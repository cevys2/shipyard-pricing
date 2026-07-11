import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Katalog Harga Docking", page_icon="🚢", layout="wide")
load_dotenv()

# --- KONEKSI DATABASE ---
@st.cache_resource
def init_connection():
    db_url = os.environ.get("SUPABASE_URL")
    if not db_url:
        try:
            db_url = st.secrets["SUPABASE_URL"]
        except Exception:
            st.error("❌ SUPABASE_URL tidak ditemukan di Secrets!")
            st.stop()
    engine = create_engine(db_url, poolclass=NullPool)
    return engine

engine = init_connection()

# --- LOAD DATA ---
@st.cache_data(ttl=600)
def load_data():
    query = """
    SELECT 
        id, nama_perusahaan, nama_kapal, tahun, 
        kategori_pekerjaan, uraian_pekerjaan, 
        volume_satuan, harga_satuan
    FROM tabel_katalog_harga
    ORDER BY nama_kapal, id
    """
    df = pd.read_sql(query, engine)
    
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
    st.error(f"❌ Gagal nyambung ke database. Error: {e}")
    st.stop()

# --- STYLING CSS CUSTOM (MENIRU SCREENSHOT) ---
st.markdown("""
    <style>
    /* Mengubah warna Sidebar menjadi Biru seperti referensi */
    [data-testid="stSidebar"] {
        background-color: #1a64bc !important;
    }
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    
    /* Mengubah warna latar belakang aplikasi agar sedikit abu muda / putih bersih */
    .stApp {
        background-color: #f4f7f6;
    }
    
    /* Kotak biru pembungkus filter */
    .filter-banner {
        background-color: #1a64bc;
        padding: 15px;
        border-radius: 8px 8px 0px 0px;
        color: white;
        font-weight: bold;
    }
    
    /* Mengurangi jarak kosong di atas */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# --- HEADER & TOMBOL EXPORT/IMPORT ---
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown("<h2 style='margin-bottom:0px; color:#1a64bc;'>Analisis Harga Satuan Docking</h2>", unsafe_allow_html=True)
with header_col2:
    # Jejerin tombol di kanan atas mirip gambar
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("📥 Import", use_container_width=True)
    with btn_col2:
        st.button("📤 Export", type="primary", use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- SIDEBAR (KOSONGAN UNTUK MENU NAVBAR) ---
st.sidebar.markdown("### ⚙️ Menu Navigasi")
st.sidebar.markdown("📁 Laporan")
st.sidebar.markdown("📊 Analisis Harga")
st.sidebar.markdown("👥 Manajemen Pengguna")

# --- FILTER HORIZONTAL (DI ATAS TABEL) ---
st.markdown('<div class="filter-banner">Pencarian & Filter Data</div>', unsafe_allow_html=True)

# Membagi baris filter menjadi 5 kolom
f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns(5)

with f_col1:
    search_query = st.text_input("Cari Pekerjaan", placeholder="Ketik di sini...")

with f_col2:
    list_perusahaan = ["Semua"] + list(df_raw['nama_perusahaan'].dropna().unique())
    filter_perusahaan = st.selectbox("Klien / Pemilik", list_perusahaan)

with f_col3:
    df_filtered_kapal = df_raw[df_raw['nama_perusahaan'] == filter_perusahaan] if filter_perusahaan != "Semua" else df_raw
    list_kapal = ["Semua"] + list(df_filtered_kapal['nama_kapal'].dropna().unique())
    filter_kapal = st.selectbox("Nama Kapal", list_kapal, key=f"kapal_{filter_perusahaan}")

with f_col4:
    list_kategori = ["Semua"] + list(df_raw['kategori_pekerjaan'].dropna().unique())
    filter_kategori = st.selectbox("Kategori", list_kategori)

with f_col5:
    list_perjanjian = ["Semua"] + list(df_raw['jenis_perjanjian'].dropna().unique())
    filter_perjanjian = st.selectbox("Jenis Perjanjian", list_perjanjian)


# --- TERAPKAN FILTER ---
df_final = df_raw.copy()
if filter_perusahaan != "Semua": df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]
if filter_kapal != "Semua": df_final = df_final[df_final['nama_kapal'] == filter_kapal]
if filter_perjanjian != "Semua": df_final = df_final[df_final['jenis_perjanjian'] == filter_perjanjian]
if filter_kategori != "Semua": df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]
if search_query: df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]

# Rapikan nama kolom
df_tampil = df_final[['id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'jenis_perjanjian', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan']].copy()
df_tampil.columns = ['ID Referensi', 'Perusahaan', 'Kapal', 'Tahun', 'Jenis Perjanjian', 'Kategori', 'Uraian Pekerjaan', 'Satuan', 'Harga Satuan']

# --- TABEL UTAMA ---
if df_final.empty:
    st.warning("⚠️ Data tidak ditemukan.")
else:
    tab1, tab2 = st.tabs(["👁️ View Data", "✏️ Mode Edit"])
    
    with tab1:
        df_view = df_tampil.copy()
        df_view['Harga Satuan'] = df_view['Harga Satuan'].apply(lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "-")
        st.dataframe(df_view, width='stretch', hide_index=True, height=600)
        
    with tab2:
        edited_df = st.data_editor(
            df_tampil,
            num_rows="dynamic",
            width='stretch',
            height=550,
            hide_index=True,
            key="tabel_editor"
        )
        
        # Tombol simpan masih sebagai placeholder
        if st.button("💾 Simpan Perubahan ke Database", type="primary"):
            st.info("UI sudah siap! Tahap selanjutnya kita akan hubungkan logika tombol ini untuk melakukan INSERT/UPDATE ke Supabase.")
