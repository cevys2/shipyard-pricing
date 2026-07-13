import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Dukuh Raya Maintenance", page_icon="🚢", layout="wide")
load_dotenv()

# --- STYLING CSS CUSTOM (TETAP SAMA) ---
st.markdown("""
    <style>
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

# --- INISIALISASI DATABASE ENGINE ---
@st.cache_resource
def init_engine():
    db_url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    if not db_url:
        st.error("❌ SUPABASE_URL tidak ditemukan di Secrets!")
        st.stop()
        
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
        
    return create_engine(db_url, poolclass=NullPool)

engine = init_engine()

# --- LOAD DATA PURE PYTHON + NULLPOOL ---
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
    
    df['nama_perusahaan'] = df['nama_perusahaan'].fillna('-').astype(str)
    df['nama_kapal'] = df['nama_kapal'].fillna('-').astype(str)
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

# --- SIDEBAR: LOGO & FILTER (TETAP SAMA) ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/984/984233.png", width=120)
st.sidebar.markdown("---")

st.sidebar.markdown("### 🔍 Filter Data")
search_query = st.sidebar.text_input("🔎 Cari Uraian...", placeholder="Contoh: Plat, Pipa...")

list_perusahaan = ["Semua"] + list(df_raw['nama_perusahaan'].dropna().unique())
filter_perusahaan = st.sidebar.selectbox("🏢 Klien / Pemilik", list_perusahaan)

df_filtered_kapal = df_raw[df_raw['nama_perusahaan'] == filter_perusahaan] if filter_perusahaan != "Semua" else df_raw
list_kapal = ["Semua"] + list(df_filtered_kapal['nama_kapal'].dropna().unique())
filter_kapal = st.sidebar.selectbox("⛴️ Nama Kapal", list_kapal, key=f"kapal_{filter_perusahaan}")

list_tahun = ["Semua"] + list(df_raw['tahun'].dropna().unique())
filter_tahun = st.sidebar.selectbox("📅 Tahun", list_tahun)

list_kategori = ["Semua"] + list(df_raw['kategori_pekerjaan'].dropna().unique())
filter_kategori = st.sidebar.selectbox("🛠️ Kategori Pekerjaan", list_kategori)

# --- HEADER COMPACT (TETAP SAMA) ---
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown("<h3 style='margin-bottom:5px; color:#1a64bc; line-height: 1.2;'>PT. DUKUH RAYA Shipyard<br>Docking Repair Pricing</h3>", unsafe_allow_html=True)
with header_col2:
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("📥 Import", width="stretch") # Disimpan untuk nanti
    with btn_col2:
        st.button("📤 Export", type="primary", width="stretch")

# --- TERAPKAN FILTER ---
df_final = df_raw.copy()
if filter_perusahaan != "Semua": df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]
if filter_kapal != "Semua": df_final = df_final[df_final['nama_kapal'] == filter_kapal]
if filter_tahun != "Semua": df_final = df_final[df_final['tahun'] == filter_tahun]
if filter_kategori != "Semua": df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]
if search_query: df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]

# --- MINI CARDS KPI (TETAP SAMA) ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #1f77b4;"><p class="mc-title">📋 Total Item Pekerjaan</p><p class="mc-val">{len(df_final)}</p></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #28a745;"><p class="mc-title">🏢 Total Klien</p><p class="mc-val">{df_final["nama_perusahaan"].nunique()}</p></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #ffc107;"><p class="mc-title">⛴️ Kapal Direferensikan</p><p class="mc-val">{df_final["nama_kapal"].nunique()}</p></div>', unsafe_allow_html=True)
with c4:
    unique_years = df_final["tahun"].dropna().unique()
    tahun_display = unique_years[0] if len(unique_years) == 1 and len(unique_years) > 0 else f"{len(unique_years)} Tahun"
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #dc3545;"><p class="mc-title">📅 Tahun Referensi</p><p class="mc-val">{tahun_display}</p></div>', unsafe_allow_html=True)

# --- TABEL & FORM AREA ---
df_tampil = df_final[['id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan']].copy()
df_tampil.columns = ['ID Referensi', 'Perusahaan', 'Kapal', 'Tahun', 'Kategori', 'Uraian Pekerjaan', 'Satuan', 'Harga Satuan']
df_tampil = df_tampil.reset_index(drop=True)

tab1, tab2, tab3 = st.tabs(["👁️ View Data", "➕ Tambah Data Baru", "✏️ Mode Edit"])

with tab1:
    if df_final.empty:
        st.warning("⚠️ Data tidak ditemukan.")
    else:
        df_view = df_tampil.copy()
        df_view['Harga Satuan'] = df_view['Harga Satuan'].apply(lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "-")
        st.dataframe(df_view, width="stretch", hide_index=True, height=650)

with tab2:
    st.markdown("### 📝 Formulir Penambahan Item Pekerjaan")
    st.info("💡 **Tips:** ID Referensi akan dibuat secara otomatis berdasarkan Nama Kapal dan Tahun yang Anda masukkan.")
    
    with st.form("form_tambah_data", clear_on_submit=True):
        col_form1, col_form2 = st.columns(2)
        
        with col_form1:
            input_pt = st.text_input("🏢 Nama Klien / Perusahaan", placeholder="Contoh: PT. JEMBATAN NUSANTARA")
            input_kpl = st.text_input("⛴️ Nama Kapal", placeholder="Contoh: MISHIMA")
            input_thn = st.text_input("📅 Tahun", placeholder="Contoh: 2024")
            input_kat = st.text_input("🛠️ Kategori Pekerjaan (Opsional)", placeholder="Contoh: DOCKING")
            
        with col_form2:
            input_urai = st.text_area("📝 Uraian Pekerjaan", placeholder="Ketik deskripsi pekerjaan di sini...")
            input_sat = st.text_input("📏 Satuan (Volume)", placeholder="Contoh: Kg, Ls, Unit, Titik")
            input_hrg = st.number_input("💰 Harga Satuan (Rp)", min_value=0.0, step=1000.0)
            
        submit_tambah = st.form_submit_button("💾 Simpan Data Baru", type="primary", use_container_width=True)
        
        if submit_tambah:
            if not input_kpl or not input_thn or not input_urai:
                st.error("⚠️ Nama Kapal, Tahun, dan Uraian Pekerjaan WAJIB diisi!")
            else:
                # ⚙️ LOGIKA PEMBUATAN ID OTOMATIS
                slug = str(input_kpl).strip().replace(" ", "_").upper()
                tahun_str = str(input_thn).strip()
                prefix = f"{slug}-{tahun_str}-"
                
                df_cek = df_raw[df_raw['id'].str.startswith(prefix, na=False)]
                if not df_cek.empty:
                    last_id = df_cek['id'].max()
                    try:
                        last_num = int(last_id.split('-')[-1])
                        new_num = last_num + 1
                    except:
                        new_num = len(df_cek) + 1
                else:
                    new_num = 1
                    
                new_id = f"{prefix}{new_num:03d}"
                
                # 💾 IMPLEMENTASI INSERT KE DATABASE
                try:
                    insert_query = text("""
                        INSERT INTO tabel_katalog_harga 
                        (id, nama_perusahaan, nama_kapal, tahun, kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan)
                        VALUES (:id, :pt, :kpl, :thn, :kat, :urai, :sat, :hrg)
                    """)
                    with engine.begin() as conn:
                        conn.execute(insert_query, {
                            "id": new_id, "pt": input_pt.upper(), "kpl": input_kpl.upper(), 
                            "thn": input_thn, "kat": input_kat, "urai": input_urai, 
                            "sat": input_sat, "hrg": input_hrg
                        })
                    
                    st.cache_data.clear() # Hapus cache agar data baru terbaca
                    st.success(f"✅ Data berhasil disimpan ke Database! ID: **{new_id}**")
                    st.rerun() # Refresh halaman
                except Exception as e:
                    st.error(f"❌ Gagal menyimpan data: {e}")

with tab3:
    st.info("💡 **Mode Edit:** Klik ganda pada teks atau angka di tabel untuk mengoreksi data. (Fitur tambah baris dimatikan di sini).")
    
    edited_df = st.data_editor(df_tampil, num_rows="fixed", width="stretch", height=600, hide_index=True, key="tabel_editor")
    
    if st.button("💾 Simpan Perubahan Edit", type="primary"):
        # 🔍 MENCARI BARIS MANA SAJA YANG BERUBAH
        changed_indices = []
        for i in range(len(df_tampil)):
            if not df_tampil.iloc[i].equals(edited_df.iloc[i]):
                changed_indices.append(i)
                
        if not changed_indices:
            st.warning("⚠️ Tidak ada perubahan data yang terdeteksi.")
        else:
            # 💾 IMPLEMENTASI UPDATE KE DATABASE
            try:
                update_query = text("""
                    UPDATE tabel_katalog_harga 
                    SET nama_perusahaan = :pt, nama_kapal = :kpl, tahun = :thn, 
                        kategori_pekerjaan = :kat, uraian_pekerjaan = :urai, 
                        volume_satuan = :sat, harga_satuan = :hrg
                    WHERE id = :id
                """)
                
                with engine.begin() as conn:
                    for idx in changed_indices:
                        row = edited_df.iloc[idx]
                        conn.execute(update_query, {
                            "pt": row['Perusahaan'], "kpl": row['Kapal'], "thn": row['Tahun'],
                            "kat": row['Kategori'], "urai": row['Uraian Pekerjaan'],
                            "sat": row['Satuan'], "hrg": row['Harga Satuan'], "id": row['ID Referensi']
                        })
                
                st.cache_data.clear()
                st.success(f"✅ {len(changed_indices)} baris data berhasil diperbarui di Database!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Gagal memperbarui data: {e}")
