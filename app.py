import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# --- KONFIGURASI HALAMAN ---
# Ubah layout jadi wide biar tabel makin lebar
st.set_page_config(page_title="Katalog Harga Docking", page_icon="🚢", layout="wide")

# Load environment variables untuk lokal
load_dotenv()

# --- KONEKSI DATABASE (SUPER BULLETPROOF) ---
@st.cache_resource
def init_connection():
    # 1. Coba cari di environment lokal (.env)
    db_url = os.environ.get("SUPABASE_URL")
    
    # 2. Kalau di lokal nggak ada, cari di Streamlit Secrets (Cloud)
    if not db_url:
        try:
            db_url = st.secrets["SUPABASE_URL"]
        except Exception:
            st.error("❌ SUPABASE_URL tidak ditemukan! Pastikan sudah di-set di Streamlit Secrets.")
            st.stop()
            
    # 3. Tambahan pool_pre_ping biar koneksi nggak diputus sepihak pas di Cloud
    engine = create_engine(
        db_url,
        pool_pre_ping=True, 
        pool_recycle=300
    )
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
    
    # 🛡️ PENCEGAHAN ERROR FILTER BEDA LAPTOP
    df['nama_perusahaan'] = df['nama_perusahaan'].fillna('TIDAK DIKETAHUI').astype(str)
    df['nama_kapal'] = df['nama_kapal'].fillna('TIDAK DIKETAHUI').astype(str)
    df['tahun'] = df['tahun'].fillna('-').astype(str)
    df['kategori_pekerjaan'] = df['kategori_pekerjaan'].fillna('-').astype(str)
    df['uraian_pekerjaan'] = df['uraian_pekerjaan'].fillna('-').astype(str)
    
    # 🚨 KOLOM DUMMY: Jenis Perjanjian (Karena belum ada di Database)
    # Ini biar UI-nya jalan dulu sesuai request demo lu
    df['jenis_perjanjian'] = "Induk" 
    
    return df

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"❌ Gagal nyambung ke database. Error: {e}")
    st.stop()

# --- STYLING CSS CUSTOM BIAR LEBIH CAKEP ---
st.markdown("""
    <style>
    .kpi-card {
        background-color: #f8f9fa;
        border-left: 5px solid #1f77b4;
        padding: 10px 15px;
        border-radius: 5px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .kpi-title {
        margin: 0;
        font-size: 13px;
        color: #6c757d;
        font-weight: bold;
        text-transform: uppercase;
    }
    .kpi-value {
        margin: 0;
        font-size: 24px;
        color: #212529;
        font-weight: 800;
    }
    /* Kecilin margin biar tabel cepet naik ke atas */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# --- HEADER COMPACT ---
# Bikin title agak kecilan pakai HTML biar nggak makan tempat
st.markdown("<h3 style='margin-bottom:0px; color:#1f77b4;'>🚢 Katalog Harga Satuan Docking</h3>", unsafe_allow_html=True)

# --- KPI CARDS (KECIL, NAIK KE ATAS, BERWARNA) ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
        <div class="kpi-card">
            <p class="kpi-title">📋 Total Item Pekerjaan</p>
            <p class="kpi-value">{len(df_raw)}</p>
        </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
        <div class="kpi-card" style="border-left-color: #28a745;">
            <p class="kpi-title">🏢 Total Klien</p>
            <p class="kpi-value">{df_raw['nama_perusahaan'].nunique()}</p>
        </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
        <div class="kpi-card" style="border-left-color: #ffc107;">
            <p class="kpi-title">⛴️ Total Kapal</p>
            <p class="kpi-value">{df_raw['nama_kapal'].nunique()}</p>
        </div>
    """, unsafe_allow_html=True)
with col4:
    st.markdown(f"""
        <div class="kpi-card" style="border-left-color: #dc3545;">
            <p class="kpi-title">📅 Tahun Data</p>
            <p class="kpi-value">{df_raw['tahun'].nunique()} <span style="font-size:12px; font-weight:normal;">Tahun</span></p>
        </div>
    """, unsafe_allow_html=True)


# --- SIDEBAR: FILTERING ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/984/984233.png", width=80)
st.sidebar.markdown("### 🔍 Filter Pencarian")

list_perusahaan = ["Semua"] + list(df_raw['nama_perusahaan'].dropna().unique())
filter_perusahaan = st.sidebar.selectbox("🏢 Klien / Pemilik", list_perusahaan)

if filter_perusahaan != "Semua":
    df_filtered_kapal = df_raw[df_raw['nama_perusahaan'] == filter_perusahaan]
else:
    df_filtered_kapal = df_raw

list_kapal = ["Semua"] + list(df_filtered_kapal['nama_kapal'].dropna().unique())
# KEY dinamis biar gak crash pas ganti filter
filter_kapal = st.sidebar.selectbox("⛴️ Nama Kapal", list_kapal, key=f"kapal_{filter_perusahaan}")

list_tahun = ["Semua"] + list(df_raw['tahun'].dropna().unique())
filter_tahun = st.sidebar.selectbox("📅 Tahun", list_tahun)

# --- FILTER BARU: JENIS PERJANJIAN ---
list_perjanjian = ["Semua"] + list(df_raw['jenis_perjanjian'].dropna().unique())
filter_perjanjian = st.sidebar.selectbox("📄 Jenis Perjanjian", list_perjanjian)

list_kategori = ["Semua"] + list(df_raw['kategori_pekerjaan'].dropna().unique())
filter_kategori = st.sidebar.selectbox("🛠️ Kategori Pekerjaan", list_kategori)

st.sidebar.markdown("---")
search_query = st.sidebar.text_input("🔎 Cari Spesifik (ex: Plat)", "")


# --- TERAPKAN FILTER ---
df_final = df_raw.copy()
if filter_perusahaan != "Semua":
    df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]
if filter_kapal != "Semua":
    df_final = df_final[df_final['nama_kapal'] == filter_kapal]
if filter_tahun != "Semua":
    df_final = df_final[df_final['tahun'] == filter_tahun]
if filter_perjanjian != "Semua":
    df_final = df_final[df_final['jenis_perjanjian'] == filter_perjanjian]
if filter_kategori != "Semua":
    df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]
if search_query:
    df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]


# --- DATA TABEL UTAMA (LEBIH BESAR & NAIK) ---
if df_final.empty:
    st.warning("⚠️ Data tidak ditemukan. Coba ubah filter di sebelah kiri.")
else:
    df_tampil = df_final.copy()
    # Urutan kolom ditambahkan 'Jenis Perjanjian'
    df_tampil = df_tampil[[
        'id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'jenis_perjanjian',
        'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan'
    ]]
    
    df_tampil.columns = [
        'ID Referensi', 'Perusahaan', 'Kapal', 'Tahun', 'Jenis Perjanjian',
        'Kategori', 'Uraian Pekerjaan', 'Satuan', 'Harga Satuan (Rp)'
    ]

    df_tampil['Harga Satuan (Rp)'] = df_tampil['Harga Satuan (Rp)'].apply(
        lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "-"
    )

    # Tabel dibikin full height 700px
    st.dataframe(
        df_tampil,
        use_container_width=True,
        hide_index=True,
        height=700 
    )
