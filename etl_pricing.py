import pandas as pd
import os
import re
from sqlalchemy import create_engine
import streamlit as st

def ekstrak_info_dari_nama_file(nama_file):
    """Mengekstrak Kapal, Perusahaan, dan Tahun dari nama file menggunakan Regex"""
    # Mencari pola "KMP [Nama Kapal] [Tahun opsional] ([Nama Perusahaan])"
    match = re.search(r'KMP\s+(.*?)\s*(?:\d{4})?\s*\((.*?)\)', nama_file, re.IGNORECASE)
    
    # Mencari tahun (4 digit angka)
    tahun_match = re.search(r'(\d{4})', nama_file)
    
    kapal = match.group(1).strip() if match else "KAPAL TIDAK DIKETAHUI"
    perusahaan = match.group(2).strip() if match else "PERUSAHAAN TIDAK DIKETAHUI"
    tahun = tahun_match.group(1) if tahun_match else "2024" # Default tahun jika tidak ada
    
    return perusahaan, kapal, tahun

def is_romawi(teks):
    """Mendeteksi apakah sebuah teks adalah angka Romawi (I, II, III, dst)"""
    teks = str(teks).strip().upper()
    pola_romawi = r'^(?=[MDCLXVI])M*(C[MD]|D?C*)(X[CL]|L?X*)(I[XV]|V?I*)$'
    return bool(re.match(pola_romawi, teks))

def run_etl_pricing():
    print("🚀 Memulai proses ETL Katalog Harga...")
    
    # Ganti '.' dengan path folder lu jika CSV-nya ada di folder khusus (misal: './data_csv')
    folder_path = '.' 
    semua_file = [f for f in os.listdir(folder_path) if f.endswith('.xlsx')]
    
    if not semua_file:
        print("❌ Tidak ditemukan file CSV di folder ini.")
        return

    list_dataframe = []
    
    for file in semua_file:
        print(f"📥 Memproses file: {file}")
        perusahaan, kapal, tahun = ekstrak_info_dari_nama_file(file)
        
        # Baca CSV, lewati 6 baris pertama (kop surat)
        # header=None karena kadang header Excel berantakan saat jadi CSV
        df_raw = pd.read_csv(os.path.join(folder_path, file), skiprows=6, header=None)
        
        # Asumsi urutan kolom standar RAB:
        # 0: No, 1: Uraian Pekerjaan, 2: Volume, 3: Satuan, 4: Harga Satuan, 5: Jumlah Harga
        # Kita ambil 5 kolom pertama saja
        df_bersih = df_raw.iloc[:, 0:5].copy()
        df_bersih.columns = ['no', 'uraian_pekerjaan', 'volume_qty', 'satuan', 'harga_satuan']
        
        # Bersihkan data dari null/NaN
        df_bersih['no'] = df_bersih['no'].fillna('').astype(str).str.strip()
        df_bersih['uraian_pekerjaan'] = df_bersih['uraian_pekerjaan'].fillna('').astype(str).str.strip()
        
        # Buat kolom kategori dan isi dengan Uraian jika 'no'-nya adalah Romawi
        df_bersih['kategori_pekerjaan'] = df_bersih.apply(
            lambda row: row['uraian_pekerjaan'] if is_romawi(row['no']) else None, 
            axis=1
        )
        
        # FORWARD FILL: Copy kategori ke bawahnya
        df_bersih['kategori_pekerjaan'] = df_bersih['kategori_pekerjaan'].ffill()
        
        # FILTERING: Buang baris yang merupakan Kategori (Romawi), kosong, atau tidak punya harga
        # Kita cuma butuh baris item pekerjaan aslinya
        df_final = df_bersih[
            (~df_bersih['no'].apply(is_romawi)) & 
            (df_bersih['no'] != '') & 
            (df_bersih['harga_satuan'].notna())
        ].copy()
        
        # Bersihkan kolom angka
        df_final['volume_qty'] = pd.to_numeric(df_final['volume_qty'], errors='coerce').fillna(0)
        
        # Hapus koma/titik ribuan di harga jika terbaca sebagai string, lalu konversi ke angka
        df_final['harga_satuan'] = df_final['harga_satuan'].astype(str).str.replace(r'[^\d.]', '', regex=True)
        df_final['harga_satuan'] = pd.to_numeric(df_final['harga_satuan'], errors='coerce').fillna(0)
        
        # Suntikkan identitas Kapal & Perusahaan
        df_final['nama_perusahaan'] = perusahaan
        df_final['nama_kapal'] = kapal
        df_final['tahun'] = tahun
        
        # Buang kolom 'no' karena sudah tidak dipakai
        df_final = df_final.drop(columns=['no'])
        
        # Rapikan urutan kolom sesuai skema kita
        urutan_kolom = ['nama_perusahaan', 'nama_kapal', 'tahun', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_qty', 'satuan', 'harga_satuan']
        df_final = df_final[urutan_kolom]
        
        list_dataframe.append(df_final)

    # Gabungkan semua data dari berbagai file CSV menjadi satu tabel raksasa
    df_gabungan = pd.concat(list_dataframe, ignore_index=True)
    
    print(f"✅ Ekstraksi selesai! Total data: {len(df_gabungan)} baris.")
    
    # ==========================================
    # LOAD KE SUPABASE
    # ==========================================
    print("🌐 Mengirim data ke Supabase...")
    try:
        engine = create_engine(st.secrets["SUPABASE_URL"])
        
        # if_exists='append' untuk menambah data tanpa menghapus yang lama
        # if_exists='replace' untuk menimpa ulang tabel dari nol (Pilih salah satu)
        # Untuk saat ini kita pakai replace dulu untuk memastikan struktur awal rapi
        df_gabungan.to_sql('tabel_katalog_harga', engine, if_exists='replace', index=False)
        
        print("🎉 Proses ETL selesai! Data berhasil masuk ke 'tabel_katalog_harga' di Supabase.")
    except Exception as e:
        print(f"❌ [Error] Gagal mengirim data ke Supabase: {e}")

if __name__ == "__main__":
    run_etl_pricing()