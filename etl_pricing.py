import pandas as pd
import os
import re
from sqlalchemy import create_engine
import streamlit as st
import hashlib
from datetime import datetime

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
    
    # Ganti '.' dengan path folder lu jika Excel-nya ada di folder khusus (misal: './data_excel')
    folder_path = '.' 
    semua_file = [f for f in os.listdir(folder_path) if f.endswith('.xlsx')]
    
    if not semua_file:
        print("❌ Tidak ditemukan file Excel di folder ini.")
        return

    list_dataframe = []
    
    for file in semua_file:
        file_path = os.path.join(folder_path, file)
        print(f"📥 Memproses file: {file}")
        
        perusahaan, kapal, year = ekstrak_info_dari_nama_file(file)
        
        try:
            # Baca file utuh dari atas buat nyari jangkar Qty
            df_raw = pd.read_excel(file_path, header=None)
        except PermissionError:
            print(f"   ❌ GAGAL BACA: Tutup dulu file Excel '{file}' ya!")
            continue
        
        # --- CARI KOORDINAT JANGKAR QTY ---
        idx_qty = None
        for r in range(min(15, len(df_raw))):
            for c in range(len(df_raw.columns)):
                val = str(df_raw.iloc[r, c]).strip().lower()
                if 'qty' in val:
                    idx_qty = c
                    break
            if idx_qty is not None:
                break
        
        if idx_qty is None:
            print(f"   ⚠️ Kolom 'Qty' tidak ditemukan di {file}. File dilewati.")
            continue
            
        # Kunci posisi tetangganya
        idx_sat = idx_qty + 1
        idx_harga = idx_qty + 2   
        # -----------------------------------
        
        # Gabungkan uraian pekerjaan yang menjorok
        uraian_cols = df_raw.iloc[:, 1:idx_qty].fillna('').astype(str)
        uraian_gabungan = uraian_cols.agg(' '.join, axis=1).str.replace(r'\s+', ' ', regex=True).str.strip()
        
        df_bersih = pd.DataFrame()
        df_bersih['no'] = df_raw.iloc[:, 0].fillna('').astype(str).str.strip()
        df_bersih['uraian_pekerjaan'] = uraian_gabungan
        
        # --- VOLUME_QTY RESMI DIHAPUS DARI SINI ---
        df_bersih['volume_satuan'] = df_raw.iloc[:, idx_sat]
        df_bersih['harga_satuan'] = df_raw.iloc[:, idx_harga]
        
        # Kategori
        df_bersih['kategori_pekerjaan'] = df_bersih.apply(
            lambda row: row['uraian_pekerjaan'] if is_romawi(row['no']) else None, 
            axis=1
        )
        df_bersih['kategori_pekerjaan'] = df_bersih['kategori_pekerjaan'].ffill()
        
        # Pastikan Harga Satuan terbaca angka
        df_bersih['harga_satuan'] = pd.to_numeric(df_bersih['harga_satuan'], errors='coerce')
        
        # FILTERING: Buang baris header dan ambil yang harganya > 0
        df_final = df_bersih[
            (~df_bersih['no'].apply(is_romawi)) & 
            (df_bersih['uraian_pekerjaan'] != '') & 
            (df_bersih['harga_satuan'].notna()) &
            (df_bersih['harga_satuan'] > 0)
        ].copy()
        
        # Bersihkan teks satuan dari tulisan 'nan'
        df_final['volume_satuan'] = df_final['volume_satuan'].fillna('-').astype(str).str.strip()
        df_final['volume_satuan'] = df_final['volume_satuan'].replace('nan', '-')
        
        # Identitas & ID Gampang Dicari
        df_final['nama_perusahaan'] = perusahaan
        df_final['nama_kapal'] = kapal
        df_final['tahun'] = year
        
        slug_kapal = str(kapal).replace(" ", "_").upper()
        df_final = df_final.reset_index(drop=True)
        # Bikin nomor urut: 001, 002, 003...
        df_final['id'] = df_final.index + 1
        df_final['id'] = df_final.apply(
            lambda x: f"{slug_kapal}-{year}-{x['id']:03d}", axis=1
        )
        
        df_final['created_at'] = datetime.now()
        
        # URUTAN FINAL (Tanpa volume_qty)
        urutan_kolom = [
            'id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'kategori_pekerjaan', 
            'uraian_pekerjaan', 'volume_satuan', 'harga_satuan', 'created_at'
        ]
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
        df_gabungan.to_sql('tabel-katalog-harga', engine, if_exists='replace', index=False)
        
        print("🎉 Proses ETL selesai! Data berhasil masuk ke 'tabel-katalog-harga' di Supabase.")
    except Exception as e:
        print(f"❌ [Error] Gagal mengirim data ke Supabase: {e}")

if __name__ == "__main__":
    run_etl_pricing()