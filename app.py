import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Katalog Harga Docking", page_icon="🚢", layout="wide")
load_dotenv()

# --- STYLING CSS CUSTOM (BERSIH & NATIVE) ---
st.markdown("""
    <style>
    /* Mengurangi jarak kosong berlebih di atas layar */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    
    /* Mempercantik tombol export/import biar seragam */
    .stButton > button { font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- HEADER & TOMBOL EXPORT/IMPORT ---
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown("<h2 style='margin-bottom:0px; color:#1a64bc;'>Analisis Harga Satuan Docking</h2>", unsafe_allow_html=True)
with header_col2:
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("📥 Import Excel", width="stretch")
    with btn_col2:
        st.button("📤 Export CSV", type="primary", width="stretch")

st.markdown("<hr style='margin-top: 10px; margin-bottom: 10px;'>", unsafe_allow_html=True)

# --- LOAD DATA PURE PYTHON (ANTI-SEGFAULT) ---
def load_data():
    db_url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    
    if not db_url:
        st.error("❌ SUPABASE_URL tidak ditemukan di Secrets!")
        st.stop()
        
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
        
    conn = st.connection("supabase", type="sql", url=db_url)
    
    query = """
    SELECT 
        id, nama_perusahaan, nama_kapal, tahun, 
        kategori_pekerjaan, uraian_pekerjaan, 
        volume_satuan, harga_satuan
    FROM tabel_katalog_harga
    ORDER BY nama_kapal, id
    """
    
    df = conn.query(query, ttl=600)
    
    df['nama_perusahaan'] = df['nama_perusahaan'].fillna('TIDAK DIKETAHUI').astype(str)
    df['nama_kapal'] = df['nama_kapal'].fillna('TIDAK DIKETAHUI').astype(str)
    df['tahun'] = df['tahun'].fillna('-').astype(str)
    df['kategori_pekerjaan'] = df['kategori_pekerjaan'].fillna('-').astype(str)
    df['uraian_pekerjaan'] = df['uraian_pekerjaan'].fillna('-').astype(str)
    df['jenis_perjanjian'] = "Induk" 
    
    return df

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"❌ Gagal mengambil data dari database. Error: {e}")
    st.stop()

# --- SIDEBAR: PENYARING DATA BERSAHABAT DENGAN TEMA ---
st.sidebar.markdown("### 🔍 Filter Data")

search_query = st.sidebar.text_input("🔎 Cari Uraian...", placeholder="Contoh: Plat, Pipa...")

list_perusahaan = ["Semua"] + list(df_raw['nama_perusahaan'].dropna().unique())
filter_perusahaan = st.sidebar.selectbox("🏢 Klien / Pemilik", list_perusahaan)

df_filtered_kapal = df_raw[df_raw['nama_perusahaan'] == filter_perusahaan] if filter_perusahaan != "Semua" else df_raw
list_kapal = ["Semua"] + list(df_filtered_kapal['nama_kapal'].dropna().unique())
filter_kapal = st.sidebar.selectbox("⛴️ Nama Kapal", list_kapal, key=f"kapal_{filter_perusahaan}")

list_tahun = ["Semua"] + list(df_raw['tahun'].dropna().unique())
filter_tahun = st.sidebar.selectbox("📅 Tahun", list_tahun)

list_perjanjian = ["Semua"] + list(df_raw['jenis_perjanjian'].dropna().unique())
filter_perjanjian = st.sidebar.selectbox("📄 Jenis Perjanjian", list_perjanjian)

list_kategori = ["Semua"] + list(df_raw['kategori_pekerjaan'].dropna().unique())
filter_kategori = st.sidebar.selectbox("🛠️ Kategori Pekerjaan", list_kategori)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Menu Tambahan")
st.sidebar.markdown("📁 Laporan Lengkap")
st.sidebar.markdown("👥 Kelola Akses")

# --- TERAPKAN FILTER ---
df_final = df_raw.copy()
if filter_perusahaan != "Semua": df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]
if filter_kapal != "Semua": df_final = df_final[df_final['nama_kapal'] == filter_kapal]
if filter_tahun != "Semua": df_final = df_final[df_final['tahun'] == filter_tahun]
if filter_perjanjian != "Semua": df_final = df_final[df_final['jenis_perjanjian'] == filter_perjanjian]
if filter_kategori != "Semua": df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]
if search_query: df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]

df_tampil = df_final[['id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'jenis_perjanjian', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan']].copy()
df_tampil.columns = ['ID Referensi', 'Perusahaan', 'Kapal', 'Tahun', 'Jenis Perjanjian', 'Kategori', 'Uraian Pekerjaan', 'Satuan', 'Harga Satuan']

# --- TABEL UTAMA & EDITOR ---
if df_final.empty:
    st.warning("⚠️ Data tidak ditemukan. Silakan ubah filter di sidebar.")
else:
    tab1, tab2 = st.tabs(["👁️ View Data", "✏️ Mode Edit (Ketik Langsung)"])
    
    with tab1:
        df_view = df_tampil.copy()
        df_view['Harga Satuan'] = df_view['Harga Satuan'].apply(lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "-")
        st.dataframe(df_view, width="stretch", hide_index=True, height=600)
        
    with tab2:
        st.info("💡 **Cara Edit:** Klik ganda pada sel untuk mengubah data. **Cara Tambah Data:** Scroll ke baris paling bawah, klik baris yang kosong/pudar, lalu ketik data baru.")
        
        edited_df = st.data_editor(
            df_tampil,
            num_rows="dynamic", 
            width="stretch",
            height=550,
            hide_index=True,
            key="tabel_editor"
        )
        
        if st.button("💾 Simpan Perubahan Langsung", type="primary"):
            st.success("Tampilan Edit berhasil! Nanti kita hubungkan data hasil editan ini ke database Supabase biar tersimpan permanen.")
