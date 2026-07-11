import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Katalog Harga Docking", page_icon="🚢", layout="wide")

# Load environment variables (.env)
load_dotenv()

# --- KONEKSI DATABASE ---
@st.cache_resource
def init_connection():
    # Coba ambil dari environment/env lokal dulu
    db_url = os.getenv("SUPABASE_URL")
    
    # Kalau kosong (biasanya pas di cloud), ambil dari Streamlit Secrets
    if not db_url:
        try:
            db_url = st.secrets["SUPABASE_URL"]
        except FileNotFoundError:
            st.error("URL Database tidak ditemukan! Pastikan sudah set Secrets di Streamlit Cloud.")
            st.stop()
            
    engine = create_engine(db_url)
    return engine

engine = init_connection()

# --- LOAD DATA ---
@st.cache_data(ttl=600)
def load_data():
    # Query disesuaikan dengan skema tabel terbaru
    query = """
    SELECT 
        id, nama_perusahaan, nama_kapal, tahun, 
        kategori_pekerjaan, uraian_pekerjaan, 
        volume_satuan, harga_satuan
    FROM tabel_katalog_harga
    ORDER BY nama_kapal, id
    """
    df = pd.read_sql(query, engine)
    
    # 🛡️ TAMBAHAN DARURAT ANTI-ERROR BEDA LAPTOP 🛡️
    # Paksa semua kolom yang mau difilter jadi string dan hilangkan NaN
    df['nama_perusahaan'] = df['nama_perusahaan'].fillna('TIDAK DIKETAHUI').astype(str)
    df['nama_kapal'] = df['nama_kapal'].fillna('TIDAK DIKETAHUI').astype(str)
    df['tahun'] = df['tahun'].fillna('-').astype(str)
    df['kategori_pekerjaan'] = df['kategori_pekerjaan'].fillna('-').astype(str)
    df['uraian_pekerjaan'] = df['uraian_pekerjaan'].fillna('-').astype(str)
    
    return df

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"❌ Gagal nyambung ke database. Cek lagi URL Supabase lu. Error: {e}")
    st.stop()

# --- SIDEBAR: FILTERING ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/984/984233.png", width=100) # Logo kapal
st.sidebar.header("🔍 Filter Katalog")

# Filter Klien / Perusahaan
list_perusahaan = ["Semua"] + list(df_raw['nama_perusahaan'].dropna().unique())
filter_perusahaan = st.sidebar.selectbox("🏢 Klien / Pemilik", list_perusahaan)

# Filter Kapal (Dinamis bergantung pada Klien yang dipilih)
if filter_perusahaan != "Semua":
    df_filtered_kapal = df_raw[df_raw['nama_perusahaan'] == filter_perusahaan]
else:
    df_filtered_kapal = df_raw

list_kapal = ["Semua"] + list(df_filtered_kapal['nama_kapal'].dropna().unique())

# 🛡️ TAMBAHAN KUNCI DINAMIS DI SINI 🛡️
# Kita bikin 'key' yang berubah tiap kali perusahaannya berubah
filter_kapal = st.sidebar.selectbox(
    "⛴️ Nama Kapal", 
    list_kapal,
    key=f"filter_kapal_{filter_perusahaan}" 
)

# Filter Tahun
list_tahun = ["Semua"] + list(df_raw['tahun'].dropna().unique())
filter_tahun = st.sidebar.selectbox("📅 Tahun", list_tahun)

# Filter Kategori Pekerjaan
list_kategori = ["Semua"] + list(df_raw['kategori_pekerjaan'].dropna().unique())
filter_kategori = st.sidebar.selectbox("🛠️ Kategori Pekerjaan", list_kategori)

# PENCARIAN TEKS (Search Bar)
search_query = st.sidebar.text_input("🔎 Cari Uraian Pekerjaan...", "")

# --- TERAPKAN FILTER ---
df_final = df_raw.copy()
if filter_perusahaan != "Semua":
    df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]
if filter_kapal != "Semua":
    df_final = df_final[df_final['nama_kapal'] == filter_kapal]
if filter_tahun != "Semua":
    df_final = df_final[df_final['tahun'] == filter_tahun]
if filter_kategori != "Semua":
    df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]
if search_query:
    # Filter pencarian teks case-insensitive
    df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]

# --- MAIN DASHBOARD ---
st.title("🚢 Katalog Harga Satuan Docking")
st.markdown("Database referensi historis harga satuan pekerjaan galangan kapal.")

# --- KPI / SUMMARY ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="Total Item Pekerjaan", value=f"{len(df_final)} Item")
with col2:
    # Mengubah Rata-rata Harga Satuan menjadi Total Perusahaan
    total_perusahaan = df_final['nama_perusahaan'].nunique()
    st.metric(label="Total Perusahaan", value=f"{total_perusahaan} Klien")
with col3:
    total_kapal = df_final['nama_kapal'].nunique()
    st.metric(label="Total Kapal Direferensikan", value=f"{total_kapal} Kapal")

st.divider()

# --- DATA TABEL UTAMA ---
st.subheader("📋 Detail Uraian Harga")

if df_final.empty:
    st.warning("Data tidak ditemukan. Coba ubah filter di sebelah kiri.")
else:
    # Rapikan nama kolom untuk tampilan UI biar enak dibaca
    df_tampil = df_final.copy()
    df_tampil.columns = [
        'ID Referensi', 'Perusahaan', 'Kapal', 'Tahun', 
        'Kategori', 'Uraian Pekerjaan', 'Satuan', 'Harga Satuan (Rp)'
    ]

    # Format angka ke Rupiah dengan pemisah ribuan koma
    df_tampil['Harga Satuan (Rp)'] = df_tampil['Harga Satuan (Rp)'].apply(
        lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "-"
    )

    # Tampilkan tabel interaktif
    st.dataframe(
        df_tampil,
        use_container_width=True,
        hide_index=True,
        height=500
    )
