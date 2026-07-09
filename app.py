import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# ==========================================
# 1. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(
    page_title="Dashboard Harga Shipyard",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="collapsed" # Sengaja di-collapse biar layar tabel makin lega
)

# ==========================================
# 2. SISTEM KEAMANAN (PASSWORD GATE)
# ==========================================
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PIN"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 Masukkan PIN Dashboard", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 Masukkan PIN Dashboard", type="password", on_change=password_entered, key="password")
        st.error("❌ PIN salah. Silakan coba lagi.")
        return False
    else:
        return True

# ==========================================
# 3. KONEKSI & CACHING DATABASE
# ==========================================
@st.cache_resource
def init_connection():
    return create_engine(st.secrets["SUPABASE_URL"])

@st.cache_data(ttl="1d")
def fetch_all_data():
    engine = init_connection()
    try:
        # Nanti saat tabel benar-benar ada di Supabase, query ini akan berjalan mulus
        df = pd.read_sql("SELECT * FROM tabel_katalog_harga", engine)
        return df
    except Exception as e:
        return pd.DataFrame() # Return DF kosong kalau belum ada data

# ==========================================
# 4. ANTARMUKA UTAMA (MAIN APP)
# ==========================================
def main():
    if not check_password():
        st.stop()

    df = fetch_all_data()

    if df.empty:
        st.warning("⚠️ Data belum tersedia. Silakan jalankan script ETL terlebih dahulu.")
        st.stop()

    # --- HEADER & PENCARIAN (Mirip Referensi UI) ---
    header_col1, header_col2 = st.columns([3, 1])
    
    with header_col1:
        st.title("🚢 Katalog Harga Pekerjaan")
        
    with header_col2:
        st.write("") # Kasih jarak sedikit biar pas di tengah
        st.write("")
        # Search bar di kanan atas, label disembunyikan biar clean
        cari_item = st.text_input("Pencarian", placeholder="🔎 Cari uraian pekerjaan...", label_visibility="collapsed")

    st.divider()

    # --- FILTER BERJENJANG (Di atas tabel) ---
    st.markdown("**Filter Data**")
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        list_perusahaan = ["Semua"] + list(df['nama_perusahaan'].dropna().unique())
        pilih_perusahaan = st.selectbox("🏢 Perusahaan", list_perusahaan, label_visibility="collapsed")

    with filter_col2:
        if pilih_perusahaan != "Semua":
            df_filter_kapal = df[df['nama_perusahaan'] == pilih_perusahaan]
        else:
            df_filter_kapal = df
        list_kapal = ["Semua"] + list(df_filter_kapal['nama_kapal'].dropna().unique())
        pilih_kapal = st.selectbox("⛴️ Kapal", list_kapal, label_visibility="collapsed")

    with filter_col3:
        list_tahun = ["Semua"] + list(df['tahun'].dropna().astype(str).unique())
        pilih_tahun = st.selectbox("📅 Tahun", list_tahun, label_visibility="collapsed")

    # --- LOGIKA FILTERING ---
    df_hasil = df.copy()

    if pilih_perusahaan != "Semua":
        df_hasil = df_hasil[df_hasil['nama_perusahaan'] == pilih_perusahaan]
    if pilih_kapal != "Semua":
        df_hasil = df_hasil[df_hasil['nama_kapal'] == pilih_kapal]
    if pilih_tahun != "Semua":
        df_hasil = df_hasil[df_hasil['tahun'].astype(str) == str(pilih_tahun)]
    if cari_item:
        df_hasil = df_hasil[df_hasil['uraian_pekerjaan'].str.contains(cari_item, case=False, na=False)]

    # --- AREA TABEL DATA ---
    st.markdown(f"*Menampilkan **{len(df_hasil)}** baris data*")

    if not df_hasil.empty:
        df_tampil = df_hasil[[
            'tahun', 'nama_perusahaan', 'nama_kapal', 
            'kategori_pekerjaan', 'uraian_pekerjaan', 
            'volume_qty', 'satuan', 'harga_satuan'
        ]].copy()
        
        # Tampilkan tabel yang membentang penuh (width=True) tanpa index nomor di kiri
        st.dataframe(
            df_tampil,
            use_container_width=True,
            hide_index=True,
            height=500 # Kunci tinggi tabel biar bisa di-scroll dengan rapi di dalam kotaknya
        )
    else:
        st.info("💡 Tidak ada data yang cocok dengan kriteria filter Anda.")

if __name__ == "__main__":
    main()
