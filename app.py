import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Dukuh Raya Maintenance", page_icon="🚢", layout="wide")
load_dotenv()

# --- STYLING CSS CUSTOM ---
st.markdown("""
    <style>
    /* MENGHILANGKAN WHITE BAR (STREAMLIT HEADER BAWAAN) */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    .stApp { background-color: #f4f7f6; } 
    .block-container { padding-top: 1rem; padding-bottom: 1.5rem; }
    
    .mini-card {
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 15px;
        background-color: transparent;
    }
    .mc-title { font-size: 11px; color: #888; font-weight: bold; text-transform: uppercase; margin-bottom: 0px; }
    .mc-val { font-size: 20px; font-weight: 800; margin-top: 0px; margin-bottom: 0px; }
    </style>
""", unsafe_allow_html=True)

# --- HEADER COMPACT (JUDUL BARU) ---
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    # Memakai line-height agar jarak antar baris rapi
    st.markdown("<h3 style='margin-bottom:5px; color:#1a64bc; line-height: 1.2;'>PT. DUKUH RAYA Shipyard<br>Docking Repair Pricing</h3>", unsafe_allow_html=True)
with header_col2:
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("📥 Import", width="stretch")
    with btn_col2:
        st.button("📤 Export", type="primary", width="stretch")

# --- LOAD DATA PURE PYTHON + NULLPOOL ---
@st.cache_data(ttl=600)
def load_data():
    db_url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    if not db_url:
        st.error("❌ SUPABASE_URL tidak ditemukan di Secrets!")
        st.stop()
        
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
        
    engine = create_engine(db_url, poolclass=NullPool)
    
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
    st.error(f"❌ Gagal mengambil data. Error: {e}")
    st.stop()

# --- SIDEBAR: PENYARING DATA ---
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

# --- TERAPKAN FILTER SEBELUM MEMBUAT CARD ---
df_final = df_raw.copy()
if filter_perusahaan != "Semua": df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]
if filter_kapal != "Semua": df_final = df_final[df_final['nama_kapal'] == filter_kapal]
if filter_tahun != "Semua": df_final = df_final[df_final['tahun'] == filter_tahun]
if filter_perjanjian != "Semua": df_final = df_final[df_final['jenis_perjanjian'] == filter_perjanjian]
if filter_kategori != "Semua": df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]
if search_query: df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]

# --- MINI CARDS KPI BERWARNA (SEKARANG DINAMIS) ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #1f77b4;"><p class="mc-title">📋 Total Item Pekerjaan</p><p class="mc-val">{len(df_final)}</p></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #28a745;"><p class="mc-title">🏢 Total Klien</p><p class="mc-val">{df_final["nama_perusahaan"].nunique()}</p></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #ffc107;"><p class="mc-title">⛴️ Kapal Direferensikan</p><p class="mc-val">{df_final["nama_kapal"].nunique()}</p></div>', unsafe_allow_html=True)
with c4:
    # Logika untuk menampilkan Tahun secara spesifik
    unique_years = df_final["tahun"].dropna().unique()
    if len(unique_years) == 1:
        tahun_display = unique_years[0]
    else:
        tahun_display = f"{len(unique_years)} Tahun"
        
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #dc3545;"><p class="mc-title">📅 Tahun Referensi</p><p class="mc-val">{tahun_display}</p></div>', unsafe_allow_html=True)

# --- TABEL UTAMA & EDITOR ---
# Reset index untuk keamanan data editor
df_tampil = df_final[['id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'jenis_perjanjian', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan']].copy()
df_tampil.columns = ['ID Referensi', 'Perusahaan', 'Kapal', 'Tahun', 'Jenis Perjanjian', 'Kategori', 'Uraian Pekerjaan', 'Satuan', 'Harga Satuan']
df_tampil = df_tampil.reset_index(drop=True)

if df_final.empty:
    st.warning("⚠️ Data tidak ditemukan. Silakan ubah filter di sidebar.")
else:
    tab1, tab2 = st.tabs(["👁️ View Data", "✏️ Mode Edit (Ketik Langsung)"])
    
    with tab1:
        df_view = df_tampil.copy()
        df_view['Harga Satuan'] = df_view['Harga Satuan'].apply(lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "-")
        st.dataframe(df_view, width="stretch", hide_index=True, height=650)
        
    with tab2:
        st.info("💡 **Cara Edit:** Klik ganda pada sel. **Cara Tambah Data:** Scroll ke baris paling bawah dan ketik di baris kosong.")
        edited_df = st.data_editor(df_tampil, num_rows="dynamic", width="stretch", height=600, hide_index=True, key="tabel_editor")
        
        if st.button("💾 Simpan Perubahan Langsung", type="primary"):
            st.success("Tampilan Edit berhasil! Backend akan dihubungkan di fase berikutnya.")
