import pandas as pd
import os
import re
from sqlalchemy import create_engine, text
import streamlit as st
from datetime import datetime
import warnings

# Mengabaikan warning dari openpyxl yang suka rewel soal header/footer excel
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

def ekstrak_kapal_tahun(nama_file):
    """Mengekstrak Kapal dan Tahun dari nama file yang formatnya ambyar"""
    tahun_match = re.search(r'(\d{4})', nama_file)
    tahun = tahun_match.group(1) if tahun_match else "2026"
    
    match = re.search(r'KMP[\.\s_]+([A-Za-z0-9\s]+?)(?:_|\s+thn|_?\(|\.xls|\.xlsx)', nama_file, re.IGNORECASE)
    if match:
        kapal = match.group(1).strip().replace('_', ' ').upper()
    else:
        kapal = "KAPAL_TIDAK_DIKETAHUI"
        
    return kapal, tahun

def cari_nama_klien(df_raw):
    """Mesin Scanner Footer untuk mencari nama Pihak Pertama / Pengguna Jasa"""
    df_bawah = df_raw.tail(50).fillna('').astype(str).apply(lambda x: x.str.upper())
    
    for r in range(len(df_bawah)):
        for c in range(len(df_bawah.columns)):
            val = df_bawah.iloc[r, c]
            if "PIHAK PERTAMA" in val or "PENGGUNA JASA" in val:
                for i in range(1, 6):
                    if (r + i) < len(df_bawah):
                        teks = df_bawah.iloc[r + i, c].strip()
                        if "PT." in teks or "PT " in teks or "CV." in teks:
                            return teks.title() 
    return "PT. Jembatan Nusantara"

def is_romawi(teks):
    teks = str(teks).strip().upper()
    pola_romawi = r'^(?=[MDCLXVI])M*(C[MD]|D?C*)(X[CL]|L?X*)(I[XV]|V?I*)$'
    return bool(re.match(pola_romawi, teks))

def run_etl_pricing():
    print("🚀 Memulai proses ETL Katalog Harga v3 (Dynamic Header Radar)...")
    
    folder_path = '.' 
    semua_file = [f for f in os.listdir(folder_path) if f.endswith(('.xlsx', '.xls'))]
    
    if not semua_file:
        print("❌ Tidak ditemukan file Excel di folder ini.")
        return

    list_dataframe = []
    
    for file in semua_file:
        file_path = os.path.join(folder_path, file)
        print(f"\n📥 Memproses file: {file}")
        
        kapal, year = ekstrak_kapal_tahun(file)
        
        try:
            df_raw = pd.read_excel(file_path, header=None)
        except PermissionError:
            print(f"   ❌ GAGAL BACA: Tutup dulu file Excel '{file}' ya!")
            continue
        except Exception as e:
            print(f"   ❌ Gagal ngebaca file. Pastikan pip install xlrd & openpyxl. Error: {e}")
            continue
            
        perusahaan = cari_nama_klien(df_raw)
        print(f"   🏢 Klien: {perusahaan} | ⛴️ Kapal: {kapal} | 📅 Tahun: {year}")
        
        # ==========================================
        # 🕵️‍♂️ RADAR HEADER DINAMIS
        # ==========================================
        koordinat = {'no': 0, 'uraian': None, 'qty': None, 'satuan': None, 'harga': None}
        header_row_index = None

        for r in range(min(60, len(df_raw))):
            baris_ini = df_raw.iloc[r].fillna('').astype(str).str.lower()
            
            ada_uraian = baris_ini.str.contains('uraian|pekerjaan').any()
            ada_harga = baris_ini.str.contains('harga|rp').any()
            
            if ada_uraian and ada_harga:
                header_row_index = r
                print(f"   🎯 Header dinamis ketemu di baris ke-{r}!")
                
                for c, val in enumerate(baris_ini):
                    val_clean = val.strip()
                    if not val_clean or val_clean == 'nan': continue
                    
                    if ('uraian' in val_clean or 'pekerjaan' in val_clean) and koordinat['uraian'] is None:
                        koordinat['uraian'] = c
                    elif ('qty' in val_clean or 'vol' in val_clean or 'jml' in val_clean or 'jumlah' in val_clean) and koordinat['qty'] is None:
                        koordinat['qty'] = c
                    elif ('satuan' in val_clean or 'sat' in val_clean) and koordinat['satuan'] is None:
                        koordinat['satuan'] = c
                    elif ('harga' in val_clean or 'rp' in val_clean) and koordinat['harga'] is None:
                        koordinat['harga'] = c
                break 

        if header_row_index is None or koordinat['uraian'] is None or koordinat['harga'] is None:
            print(f"   ⚠️ Gagal memetakan header di {file}. File dilewati.")
            continue
            
        # ==========================================
        # 🧹 EKSTRAKSI & PEMBERSIHAN DATA
        # ==========================================
        # Memotong dataframe mulai dari bawah header
        df_data = df_raw.iloc[header_row_index + 1 :].copy()
        
        # Gabungkan teks uraian jika format excel-nya di-merge (dari kolom uraian sampai sebelum qty)
        batas_kanan_uraian = koordinat['qty'] if koordinat['qty'] is not None else koordinat['uraian'] + 1
        uraian_cols = df_data.iloc[:, koordinat['uraian']:batas_kanan_uraian].fillna('').astype(str)
        uraian_gabungan = uraian_cols.agg(' '.join, axis=1).str.replace(r'\s+', ' ', regex=True).str.strip()
        
        df_bersih = pd.DataFrame()
        df_bersih['no'] = df_data.iloc[:, koordinat['no']].fillna('').astype(str).str.strip()
        df_bersih['uraian_pekerjaan'] = uraian_gabungan
        
        # Tangani jika kolom satuan tidak ada (karena digabung sama qty)
        if koordinat['satuan'] is not None:
            df_bersih['volume_satuan'] = df_data.iloc[:, koordinat['satuan']]
        else:
            df_bersih['volume_satuan'] = "-"
            
        df_bersih['harga_satuan'] = df_data.iloc[:, koordinat['harga']]
        
        df_bersih['kategori_pekerjaan'] = df_bersih.apply(
            lambda row: row['uraian_pekerjaan'] if is_romawi(row['no']) else None, axis=1
        )
        df_bersih['kategori_pekerjaan'] = df_bersih['kategori_pekerjaan'].ffill()
        df_bersih['harga_satuan'] = pd.to_numeric(df_bersih['harga_satuan'], errors='coerce')
        
        df_final = df_bersih[
            (~df_bersih['no'].apply(is_romawi)) & 
            (df_bersih['uraian_pekerjaan'] != '') & 
            (df_bersih['harga_satuan'].notna()) &
            (df_bersih['harga_satuan'] > 0)
        ].copy()
        
        df_final['volume_satuan'] = df_final['volume_satuan'].fillna('-').astype(str).str.strip()
        df_final['volume_satuan'] = df_final['volume_satuan'].replace('nan', '-')
        
        df_final['nama_perusahaan'] = perusahaan
        df_final['nama_kapal'] = kapal
        df_final['tahun'] = year
        
        slug_kapal = str(kapal).replace(" ", "_").upper()
        df_final = df_final.reset_index(drop=True)
        df_final['id'] = df_final.index + 1
        df_final['id'] = df_final.apply(lambda x: f"{slug_kapal}-{year}-{x['id']:03d}", axis=1)
        df_final['created_at'] = datetime.now()
        
        urutan_kolom = [
            'id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'kategori_pekerjaan', 
            'uraian_pekerjaan', 'volume_satuan', 'harga_satuan', 'created_at'
        ]
        df_final = df_final[urutan_kolom]
        list_dataframe.append(df_final)

    # ==========================================
    # 💾 LOAD KE SUPABASE
    # ==========================================
    if list_dataframe:
        df_gabungan = pd.concat(list_dataframe, ignore_index=True)
        df_gabungan['tahun'] = df_gabungan['tahun'].astype(str)
        
        print(f"\n✅ Ekstraksi selesai! Siap memproses {len(df_gabungan)} baris data.")
        print("🌐 Terhubung ke Supabase...")
        
        try:
            engine = create_engine(st.secrets["SUPABASE_URL"])
            
            with engine.begin() as conn:
                kombinasi_unik = df_gabungan[['nama_kapal', 'tahun']].drop_duplicates()
                
                for _, row in kombinasi_unik.iterrows():
                    kapal_target = str(row['nama_kapal'])
                    tahun_target = str(row['tahun'])
                    
                    print(f"🧹 Menghapus data lama untuk: {kapal_target} - Tahun {tahun_target}...")
                    query_hapus = text("DELETE FROM tabel_katalog_harga WHERE nama_kapal = :kpl AND tahun = :thn")
                    conn.execute(query_hapus, {"kpl": kapal_target, "thn": tahun_target})
                
                print("🚀 Insert data fresh ke database...")
                df_gabungan.to_sql("tabel_katalog_harga", con=conn, if_exists='append', index=False)
                
            print("🎉 BOOM! Proses ETL selesai sempurna tanpa duplikat.")
            
        except Exception as e:
            print(f"\n❌ [ERROR FATAL] Gagal mengirim data ke Supabase:")
            print(f"Detail Error: {e}")
    else:
        print("\n❌ Tidak ada data valid yang bisa diekstrak dari file.")

if __name__ == "__main__":
    run_etl_pricing()
