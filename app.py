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
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. SISTEM KEAMANAN (PASSWORD GATE)
# ==========================================
def check_password():
    """Mengembalikan `True` jika user memasukkan password yang benar."""
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PIN"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Hapus password dari memory demi keamanan
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # User belum login, tampilkan input
        st.text_input("🔒 Masukkan PIN Dashboard", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # Password salah
        st.text_input("🔒 Masukkan PIN Dashboard", type="password", on_change=password_entered, key="password")
        st.error("❌ PIN salah. Silakan coba lagi.")
        return False
    else:
        # Password benar
        return True

# ==========================================
# 3. KONEKSI & CACHING DATABASE
# ==========================================
@st.cache_resource
def init_connection():
    """Membangun koneksi ke Supabase."""
    return create_engine(st.secrets["SUPABASE_URL"])

@st.cache_data(ttl="1d") # Cache disimpan selama 1 hari agar secepat kilat
def fetch_all_data():
    """Menarik seluruh data dari Supabase ke dalam memori Pandas."""
    engine = init_connection()
    query = "SELECT * FROM tabel_katalog_harga"
    try:
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"Gagal menarik data dari database: {e}")
        return pd.DataFrame()

# ==========================================
# 4. ANTARMUKA UTAMA (MAIN APP)
# ==========================================
def main():
    # Hentikan eksekusi jika password belum benar
    if not check_password():
        st.stop()

    # Tarik data dari database (akan terasa instan setelah load pertama karena di-cache)
    df = fetch_all_data()

    if df.empty:
        st.warning("⚠️ Data belum tersedia di database. Jalankan script ETL terlebih dahulu.")
        st.stop()

    st.title("🚢 Dashboard Katalog & Histori Harga Pekerjaan")
    st.markdown("Cari dan bandingkan harga item pekerjaan secara instan.")
    st.divider()

    # --- BAGIAN FILTER BERJENJANG ---
    st.subheader("🔍 Filter Pencarian")
    
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        list_perusahaan = ["Semua"] + list(df['nama_perusahaan'].dropna().unique())
        pilih_perusahaan = st.selectbox("🏢 Perusahaan", list_perusahaan)

    with col2:
        # Filter Kapal akan menyesuaikan pilihan Perusahaan
        if pilih_perusahaan != "Semua":
            df_filter_kapal = df[df['nama_perusahaan'] == pilih_perusahaan]
        else:
            df_filter_kapal = df
            
        list_kapal = ["Semua"] + list(df_filter_kapal['nama_kapal'].dropna().unique())
        pilih_kapal = st.selectbox("⛴️ Kapal", list_kapal)

    with col3:
        # Filter Tahun
        list_tahun = ["Semua"] + list(df['tahun'].dropna().astype(str).unique())
        pilih_tahun = st.selectbox("📅 Tahun", list_tahun)
        
    with col4:
        # Pencarian Item Pekerjaan (Text Input)
        cari_item = st.text_input("🔎 Cari Uraian Pekerjaan...", placeholder="Misal: Sandblasting")

    # --- LOGIKA PENERAPAN FILTER ---
    df_hasil = df.copy()

    if pilih_perusahaan != "Semua":
        df_hasil = df_hasil[df_hasil['nama_perusahaan'] == pilih_perusahaan]
    
    if pilih_kapal != "Semua":
        df_hasil = df_hasil[df_hasil['nama_kapal'] == pilih_kapal]
        
    if pilih_tahun != "Semua":
        df_hasil = df_hasil[df_hasil['tahun'].astype(str) == str(pilih_tahun)]
        
    if cari_item:
        # Pencarian mengabaikan huruf besar/kecil (case-insensitive)
        df_hasil = df_hasil[df_hasil['uraian_pekerjaan'].str.contains(cari_item, case=False, na=False)]

    # --- BAGIAN PENAMPILAN DATA ---
    st.divider()
    
    # Metrik Ringkasan
    st.metric("Total Item Ditemukan", f"{len(df_hasil)} Baris")

    # Menampilkan Tabel
    if not df_hasil.empty:
        # Menyusun ulang dan mengganti nama kolom agar rapi saat dibaca user
        df_tampil = df_hasil[[
            'tahun', 'nama_perusahaan', 'nama_kapal', 
            'kategori_pekerjaan', 'uraian_pekerjaan', 
            'volume_qty', 'satuan', 'harga_satuan'
        ]].copy()
        
        # Format angka harga agar ada titik ribuannya (Opsional tapi mempercantik)
        # df_tampil['harga_satuan'] = df_tampil['harga_satuan'].apply(lambda x: f"Rp {x:,.0f}")
        
        st.dataframe(
            df_tampil,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("💡 Tidak ada data yang cocok dengan kriteria filter Anda.")

if __name__ == "__main__":
    main()
