import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import streamlit_antd_components as sac

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Dukuh Raya Maintenance", page_icon="🚢", layout="wide", initial_sidebar_state="expanded")
load_dotenv()

NAMA_TABEL = "tabel_katalog_harga"

# --- STYLING CSS CUSTOM (TAILWIND / SAAS STYLE) ---
st.markdown("""
    <style>
    /* Menyembunyikan elemen bawaan Streamlit */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Background utama aplikasi */
    .stApp { background-color: #f8fafc; } 
    .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 95%; }
    
    /* --- MODERN KPI CARDS (Tailwind Style) --- */
    .kpi-container {
        display: flex;
        gap: 1rem;
        margin-bottom: 2rem;
    }
    .kpi-card {
        flex: 1;
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        border: 1px solid #e2e8f0;
        display: flex;
        flex-direction: column;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04);
    }
    .kpi-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }
    .kpi-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        border-radius: 8px;
        font-size: 18px;
    }
    .kpi-title {
        color: #64748b;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin: 0;
    }
    .kpi-val {
        color: #0f172a;
        font-size: 2rem;
        font-weight: 800;
        line-height: 1;
        margin: 0;
    }
    
    /* Warna Ikon KPI */
    .icon-blue { background-color: #eff6ff; color: #3b82f6; }
    .icon-green { background-color: #f0fdf4; color: #22c55e; }
    .icon-yellow { background-color: #fefce8; color: #eab308; }
    .icon-red { background-color: #fef2f2; color: #ef4444; }

    /* --- POLISHED LOGIN UI TWEAKS --- */
    div[data-testid="stForm"] {
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 20px 25px -5px rgba(0,0,0,0.05), 0 10px 10px -5px rgba(0,0,0,0.02); 
        padding: 2.5rem !important;
        background-color: white;
    }
    div[data-testid="stTextInput"] input {
        border-radius: 8px;
        border: 1px solid #cbd5e1;
        font-size: 15px;
        padding: 10px 15px;
        transition: all 0.2s;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
    }
    div[data-testid="stFormSubmitButton"] button {
        border-radius: 8px;
        font-weight: 700;
        letter-spacing: 0.5px;
        background-color: #0f172a;
        color: white;
        border: none;
        transition: background-color 0.2s;
    }
    div[data-testid="stFormSubmitButton"] button:hover {
        background-color: #1e293b;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# --- INISIALISASI DATABASE ENGINE ---
@st.cache_resource
def init_engine():
    db_url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    if not db_url:
        st.error("❌ SUPABASE_URL tidak ditemukan di Secrets!")
        st.stop()
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif db_url.startswith("postgresql://") and "pg8000" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
        
    return create_engine(
        db_url, 
        pool_size=10, 
        max_overflow=20, 
        pool_pre_ping=True, 
        pool_recycle=300
    )
engine = init_engine()

# --- SETUP TABEL USERS ---
@st.cache_resource
def setup_user_table():
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'user'
                )
            """))
            cek_user = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            if cek_user == 0:
                default_hash = generate_password_hash("admin123", method='pbkdf2:sha256')
                conn.execute(text("INSERT INTO users (username, password_hash, role) VALUES ('admin', :pw, 'admin')"), {"pw": default_hash})
    except Exception as e:
        st.error(f"Gagal inisialisasi users: {e}")

setup_user_table()

# --- SESSION STATE LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ''
    st.session_state['role'] = ''

# ==========================================
# 🔐 HALAMAN LOGIN (POLISHED)
# ==========================================
if not st.session_state['logged_in']:
    st.markdown("<br><br><br>", unsafe_allow_html=True) 
    
    col_kiri, col_login, col_kanan = st.columns([1.5, 1.5, 1.5])
    
    with col_login:
        st.markdown("""
            <div style='text-align: center; margin-bottom: 30px;'>
                <h1 style='color: #0f172a; font-weight: 800; margin-bottom: 0px; font-size: 2.2rem; letter-spacing: -0.025em;'>DUKUH RAYA</h1>
                <p style='color: #64748b; font-size: 0.95rem; margin-top: 5px; font-weight: 500;'>Shipyard Maintenance System</p>
            </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            login_user = st.text_input("Username", placeholder="Masukkan username admin")
            login_pass = st.text_input("Password", type="password", placeholder="••••••••")
            
            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
            submit_login = st.form_submit_button("Masuk ke Dashboard", width="stretch")
            
            if submit_login:
                if login_user and login_pass:
                    with engine.connect() as conn:
                        result = conn.execute(text("SELECT password_hash, role FROM users WHERE username = :usr"), {"usr": login_user}).fetchone()
                        
                    if result and check_password_hash(result[0], login_pass):
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = login_user
                        st.session_state['role'] = result[1]
                        st.success("Login berhasil!")
                        st.rerun()
                    else:
                        st.error("❌ Username atau Password salah!")
                else:
                    st.warning("⚠️ Harap isi username dan password.")
                    
    st.stop() 

# ==========================================
# 🚀 APLIKASI UTAMA (SETELAH LOGIN)
# ==========================================

@st.cache_data(ttl=600)
def load_data():
    query = f"""
    SELECT 
        id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun, 
        kategori_pekerjaan, uraian_pekerjaan, 
        volume_satuan, harga_satuan
    FROM {NAMA_TABEL}
    ORDER BY nama_kapal, id
    """
    df = pd.read_sql(query, engine)
    
    for col in ['nama_perusahaan', 'nama_kapal', 'tipe_perjanjian', 'tahun', 'kategori_pekerjaan']:
        df[col] = df[col].fillna('-').astype(str)
        
    df['uraian_pekerjaan'] = df['uraian_pekerjaan'].fillna('-').astype(str)
    return df

@st.cache_data(ttl=60)
def load_users():
    with engine.connect() as conn:
        return pd.read_sql("SELECT id, username, role FROM users ORDER BY id", conn)

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"❌ Gagal mengambil data. Error: {e}")
    st.stop()

# --- SIDEBAR NAVIGASI & FILTER MODERN ---
with st.sidebar:
    st.markdown("""
        <h2 style='color: #0f172a; font-weight: 800; font-size: 1.5rem; margin-bottom: 0;'>DUKUH RAYA</h2>
        <p style='color: #64748b; font-size: 0.85rem; margin-top: 0; margin-bottom: 1.5rem;'>Dashboard Admin</p>
    """, unsafe_allow_html=True)
    
    # Menu Navigasi Sidebar Palsu (untuk estetika, sebenarnya aksi log out)
    sidebar_action = sac.menu([
        sac.MenuItem(f"User: {st.session_state['username']}", icon='person-circle', disabled=True),
        sac.MenuItem('Logout', icon='box-arrow-right'),
    ], size='sm', variant='filled', color='red')
    
    if sidebar_action == 'Logout':
        st.session_state['logged_in'] = False
        st.session_state['username'] = ''
        st.session_state['role'] = ''
        st.rerun()
        
    sac.divider(label='FILTER DATA', icon='funnel', align='center', color='gray')
    
    list_perusahaan = ["Semua"] + list(df_raw['nama_perusahaan'].dropna().unique())
    filter_perusahaan = st.selectbox("🏢 Klien / Pemilik", list_perusahaan)

    df_final = df_raw 
    if filter_perusahaan != "Semua": df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]

    list_kapal = ["Semua"] + list(df_final['nama_kapal'].dropna().unique())
    filter_kapal = st.selectbox("⛴️ Nama Kapal", list_kapal)
    if filter_kapal != "Semua": df_final = df_final[df_final['nama_kapal'] == filter_kapal]

    list_kategori = ["Semua"] + list(df_final['kategori_pekerjaan'].dropna().unique())
    filter_kategori = st.selectbox("🛠️ Kategori Pekerjaan", list_kategori)
    if filter_kategori != "Semua": df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]

    list_tahun = ["Semua"] + list(df_raw['tahun'].dropna().unique())
    filter_tahun = st.selectbox("📅 Tahun", list_tahun)
    if filter_tahun != "Semua": df_final = df_final[df_final['tahun'] == filter_tahun]

    list_tipe = ["Semua"] + list(df_raw['tipe_perjanjian'].dropna().unique())
    filter_tipe = st.selectbox("📄 Tipe Perjanjian", list_tipe)
    if filter_tipe != "Semua": df_final = df_final[df_final['tipe_perjanjian'] == filter_tipe]

    search_query = st.text_input("🔎 Cari Uraian...", placeholder="Contoh: Plat, Pipa...")
    if search_query: df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]


# --- MAIN CONTENT AREA ---
st.markdown("<h2 style='color: #0f172a; font-weight: 700; font-size: 1.8rem; margin-bottom: 0.5rem;'>Overview Dashboard</h2>", unsafe_allow_html=True)

# --- MODERN MINI CARDS KPI ---
st.markdown(f"""
<div class="kpi-container">
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-blue">📋</div>
            <p class="kpi-title">Total Item</p>
        </div>
        <p class="kpi-val">{len(df_final)}</p>
    </div>
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-green">🏢</div>
            <p class="kpi-title">Total Klien</p>
        </div>
        <p class="kpi-val">{df_final["nama_perusahaan"].nunique()}</p>
    </div>
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-yellow">⛴️</div>
            <p class="kpi-title">Kapal</p>
        </div>
        <p class="kpi-val">{df_final["nama_kapal"].nunique()}</p>
    </div>
    <div class="kpi-card">
        <div class="kpi-header">
            <div class="kpi-icon icon-red">📅</div>
            <p class="kpi-title">Tahun Referensi</p>
        </div>
        <p class="kpi-val">{df_final["tahun"].nunique()}</p>
    </div>
</div>
""", unsafe_allow_html=True)

# --- DATAFRAME PREPARATION ---
df_tampil = df_final[['id', 'nama_perusahaan', 'nama_kapal', 'tipe_perjanjian', 'tahun', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan']]
df_tampil = df_tampil.rename(columns={
    'id': 'ID Referensi', 'nama_perusahaan': 'Perusahaan', 'nama_kapal': 'Kapal', 
    'tipe_perjanjian': 'Tipe Perjanjian',
    'tahun': 'Tahun', 'kategori_pekerjaan': 'Kategori', 'uraian_pekerjaan': 'Uraian Pekerjaan', 
    'volume_satuan': 'Satuan', 'harga_satuan': 'Harga Satuan'
}).reset_index(drop=True)

# --- SEGMENTED CONTROL MENU (PENGGANTI TABS) ---
menu_items = [
    sac.SegmentedItem(label='View Data', icon='table'),
    sac.SegmentedItem(label='Tambah Data Baru', icon='plus-circle-fill'),
    sac.SegmentedItem(label='Edit & Hapus', icon='pencil-square')
]

if st.session_state['role'] == 'admin':
    menu_items.append(sac.SegmentedItem(label='Kelola Akses', icon='shield-lock-fill'))

st.markdown("<br>", unsafe_allow_html=True)
selected_tab = sac.segmented(
    items=menu_items,
    format_func='title',
    align='center',
    use_container_width=True,
    color='dark',
    bg_color='#ffffff',
    divider=False
)
st.markdown("<br>", unsafe_allow_html=True)

# --- LOGIKA TAB VIEW DATA ---
if selected_tab == 'View Data': 
    if df_tampil.empty:
        st.warning("⚠️ Data tidak ditemukan.")
    else:
        st.dataframe(
            df_tampil, 
            width="stretch", 
            hide_index=True, 
            height=600,
            column_config={
                "ID Referensi": None,
                "Harga Satuan": st.column_config.NumberColumn("Harga Satuan", format="Rp %d")
            }
        )

# --- LOGIKA TAB TAMBAH DATA ---
elif selected_tab == 'Tambah Data Baru': 
    st.markdown("<h4 style='color: #0f172a;'>📝 Formulir Penambahan Item Pekerjaan (Bulk Entry)</h4>", unsafe_allow_html=True)
    
    with st.form("form_bulk_entry", clear_on_submit=True):
        st.markdown("<p style='font-weight: 600; color:#334155;'>📌 Informasi Utama (Diisi Sekali)</p>", unsafe_allow_html=True)
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1: input_pt = st.text_input("🏢 Klien / Perusahaan")
        with col_m2: input_kpl = st.text_input("⛴️ Nama Kapal")
        with col_m3: input_thn = st.text_input("📅 Tahun")
        with col_m4: input_tipe = st.selectbox("📄 Tipe Perjanjian", ["Induk", "Addendum"])
            
        st.markdown("<hr style='margin: 1rem 0; border-color: #e2e8f0;'>", unsafe_allow_html=True)
        
        st.markdown("<p style='font-weight: 600; color:#334155;'>📋 Detail Item Pekerjaan</p>", unsafe_allow_html=True)
        st.info("💡 **Tips Cepat:** Anda bisa klik tanda **'+'** di bawah tabel untuk menambah baris, atau langsung **Copy-Paste baris dari Excel** Anda langsung ke dalam tabel di bawah ini!")
        
        df_template = pd.DataFrame(columns=["Kategori Pekerjaan", "Uraian Pekerjaan", "Satuan (Volume)", "Harga Satuan"])
        
        edited_bulk = st.data_editor(
            df_template,
            num_rows="dynamic", 
            width="stretch",
            height=350,
            column_config={
                "Kategori Pekerjaan": st.column_config.TextColumn("Kategori Pekerjaan"),
                "Uraian Pekerjaan": st.column_config.TextColumn("Uraian Pekerjaan", required=True),
                "Satuan (Volume)": st.column_config.TextColumn("Satuan (Volume)"),
                "Harga Satuan": st.column_config.NumberColumn("Harga Satuan (Rp)", min_value=0.0, step=1000.0)
            }
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        submit_bulk = st.form_submit_button("💾 Simpan Semua Data Pekerjaan", type="primary", use_container_width=True)
        
        if submit_bulk:
            if not input_kpl or not input_thn:
                st.error("⚠️ Nama Kapal dan Tahun pada Informasi Utama WAJIB diisi!")
            elif edited_bulk.empty:
                st.error("⚠️ Tabel Detail Item Pekerjaan masih kosong! Silakan isi minimal 1 baris.")
            else:
                valid_rows = edited_bulk.dropna(how='all')
                if valid_rows.empty:
                    st.error("⚠️ Tidak ada data uraian pekerjaan yang valid untuk disimpan.")
                else:
                    slug = str(input_kpl).strip().replace(" ", "_").upper()
                    prefix = f"{slug}-{str(input_thn).strip()}-"
                    
                    df_cek = df_raw[df_raw['id'].str.startswith(prefix, na=False)]
                    try:
                        last_num = int(df_cek['id'].max().split('-')[-1]) if not df_cek.empty else 0
                    except:
                        last_num = len(df_cek)
                        
                    try:
                        with engine.begin() as conn:
                            insert_query = text(f"""
                                INSERT INTO {NAMA_TABEL} 
                                (id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun, kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan)
                                VALUES (:id, :pt, :kpl, :tipe, :thn, :kat, :urai, :sat, :hrg)
                            """)
                            
                            for index, row in valid_rows.iterrows():
                                last_num += 1
                                new_id = f"{prefix}{last_num:03d}"
                                
                                kat = row['Kategori Pekerjaan'] if pd.notna(row['Kategori Pekerjaan']) else "-"
                                urai = row['Uraian Pekerjaan'] if pd.notna(row['Uraian Pekerjaan']) else "-"
                                sat = row['Satuan (Volume)'] if pd.notna(row['Satuan (Volume)']) else "-"
                                hrg = row['Harga Satuan'] if pd.notna(row['Harga Satuan']) else 0.0
                                
                                conn.execute(insert_query, {
                                    "id": new_id, "pt": input_pt.upper(), "kpl": input_kpl.upper(), 
                                    "tipe": input_tipe, "thn": input_thn, "kat": kat, 
                                    "urai": urai, "sat": sat, "hrg": float(hrg)
                                })
                        
                        st.cache_data.clear()
                        st.success(f"✅ Berhasil! **{len(valid_rows)}** item pekerjaan telah disimpan.")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Gagal menyimpan data: {e}")

# --- LOGIKA TAB EDIT & HAPUS ---
elif selected_tab == 'Edit & Hapus': 
    st.info("💡 **Mode Edit:** Klik ganda pada teks untuk mengoreksi. **Untuk menghapus baris, centang kotak di kolom '❌ Hapus'.**")
    
    pilih_semua = st.checkbox("☑️ Centang Semua (Hapus Massal Data di Bawah)")
    
    df_edit_view = df_tampil.copy()
    df_edit_view.insert(0, '❌ Hapus', pilih_semua)
    
    edited_df = st.data_editor(
        df_edit_view, 
        num_rows="fixed", 
        width="stretch", 
        height=550, 
        hide_index=True, 
        key="tabel_editor",
        column_config={
            "ID Referensi": None,
            "Tipe Perjanjian": st.column_config.SelectboxColumn(
                "Tipe Perjanjian",
                options=["Induk", "Addendum"],
                required=True
            ),
            "Harga Satuan": st.column_config.NumberColumn("Harga Satuan", format="Rp %d")
        }
    )
    
    if st.button("💾 Simpan Perubahan", type="primary"):
        ids_to_delete = edited_df[edited_df['❌ Hapus'] == True]['ID Referensi'].tolist()
        
        changed_indices = []
        for i in range(len(df_tampil)):
            if df_tampil.iloc[i]['ID Referensi'] in ids_to_delete:
                continue 
            if not df_tampil.iloc[i].equals(edited_df.iloc[i].drop('❌ Hapus')):
                changed_indices.append(i)
                
        if not ids_to_delete and not changed_indices:
            st.warning("⚠️ Tidak ada perubahan yang terdeteksi.")
        else:
            try:
                with engine.begin() as conn:
                    if ids_to_delete:
                        delete_query = text(f"DELETE FROM {NAMA_TABEL} WHERE id = :id")
                        for del_id in ids_to_delete:
                            conn.execute(delete_query, {"id": del_id})
                            
                    if changed_indices:
                        update_query = text(f"""
                            UPDATE {NAMA_TABEL} 
                            SET nama_perusahaan = :pt, nama_kapal = :kpl, tipe_perjanjian = :tipe, tahun = :thn, 
                                kategori_pekerjaan = :kat, uraian_pekerjaan = :urai, 
                                volume_satuan = :sat, harga_satuan = :hrg
                            WHERE id = :id
                        """)
                        for idx in changed_indices:
                            row = edited_df.iloc[idx]
                            conn.execute(update_query, {
                                "pt": row['Perusahaan'], "kpl": row['Kapal'], "tipe": row['Tipe Perjanjian'], "thn": row['Tahun'],
                                "kat": row['Kategori'], "urai": row['Uraian Pekerjaan'],
                                "sat": row['Satuan'], "hrg": row['Harga Satuan'], "id": row['ID Referensi']
                            })
                
                st.cache_data.clear()
                msg = "✅ Berhasil! "
                if ids_to_delete: msg += f"Menghapus {len(ids_to_delete)} baris. "
                if changed_indices: msg += f"Memperbarui {len(changed_indices)} baris."
                st.success(msg)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Gagal memproses data ke database: {e}")

# --- LOGIKA TAB KELOLA AKSES ---
elif selected_tab == 'Kelola Akses' and st.session_state['role'] == 'admin':
    st.markdown("<h4 style='color: #0f172a;'>👥 Manajemen Pengguna</h4>", unsafe_allow_html=True)
    
    users_df = load_users()
        
    col_user1, col_user2 = st.columns([2, 1], gap="large")
    
    with col_user1:
        st.markdown("**Daftar Pengguna Aktif**")
        st.dataframe(users_df, width="stretch", hide_index=True)
        
        st.markdown("**Hapus Pengguna**")
        del_username = st.selectbox("Pilih Username yang akan dihapus", users_df['username'].tolist())
        if st.button("🗑️ Hapus User", type="primary"):
            if del_username == 'admin':
                st.error("⚠️ Akun admin utama tidak boleh dihapus!")
            elif del_username == st.session_state['username']:
                st.error("⚠️ Anda tidak bisa menghapus akun Anda sendiri saat sedang login!")
            else:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM users WHERE username = :usr"), {"usr": del_username})
                load_users.clear()
                st.success(f"✅ User {del_username} berhasil dihapus!")
                st.rerun()
                
    with col_user2:
        st.markdown("**Tambah Pengguna Baru**")
        with st.form("form_tambah_user", clear_on_submit=True):
            new_user = st.text_input("Username Baru")
            new_pass = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["user", "admin"])
            
            if st.form_submit_button("Tambah User", use_container_width=True):
                if not new_user or not new_pass:
                    st.error("⚠️ Username dan Password wajib diisi!")
                elif new_user in users_df['username'].values:
                    st.error("⚠️ Username sudah terdaftar!")
                else:
                    hashed_pw = generate_password_hash(new_pass, method='pbkdf2:sha256')
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO users (username, password_hash, role) VALUES (:usr, :pw, :role)"), 
                                        {"usr": new_user, "pw": hashed_pw, "role": new_role})
                    load_users.clear()
                    st.success(f"✅ Akun {new_user} berhasil dibuat!")
                    st.rerun()

        st.markdown("**🔑 Ubah Password**")
        with st.form("form_ubah_password", clear_on_submit=True):
            user_to_edit = st.selectbox("Pilih Username", users_df['username'].tolist())
            new_pass_edit = st.text_input("Password Baru", type="password")
            
            if st.form_submit_button("Update Password", use_container_width=True):
                if not new_pass_edit:
                    st.error("⚠️ Password baru tidak boleh kosong!")
                else:
                    new_hashed_pw = generate_password_hash(new_pass_edit, method='pbkdf2:sha256')
                    try:
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE users SET password_hash = :pw WHERE username = :usr"), 
                                            {"pw": new_hashed_pw, "usr": user_to_edit})
                        load_users.clear()
                        st.success(f"✅ Password untuk {user_to_edit} berhasil diubah!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Gagal mengubah password: {e}")