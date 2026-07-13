import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Dukuh Raya Maintenance", page_icon="🚢", layout="wide")
load_dotenv()

NAMA_TABEL = "tabel_katalog_harga"

# --- STYLING CSS CUSTOM ---
st.markdown("""
    <style>
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    .stApp { background-color: #f4f7f6; } 
    .block-container { padding-top: 1rem; padding-bottom: 1.5rem; }
    
    .mini-card {
        border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 6px;
        padding: 8px 12px; margin-bottom: 15px; background-color: transparent;
    }
    .mc-title { font-size: 11px; color: #888; font-weight: bold; text-transform: uppercase; margin-bottom: 0px; }
    .mc-val { font-size: 20px; font-weight: 800; margin-top: 0px; margin-bottom: 0px; }
    
    /* --- POLISHED LOGIN UI TWEAKS --- */
    div[data-testid="stForm"] {
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        border-top: 6px solid #1a64bc; 
        box-shadow: 0 15px 35px rgba(0,0,0,0.08); 
        padding: 2rem !important;
        background-color: white;
    }

    div[data-testid="stTextInput"] input {
        border-radius: 6px;
        border: 1.5px solid #cbd5e1;
        font-size: 15px;
        transition: all 0.3s;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #1a64bc;
        box-shadow: 0 0 0 2px rgba(26,100,188,0.2);
    }

    div[data-testid="stFormSubmitButton"] button {
        border-radius: 6px;
        font-weight: 800;
        letter-spacing: 1px;
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
        
    # Otomatis konversi URL Supabase agar menggunakan driver pg8000
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif db_url.startswith("postgresql://") and "pg8000" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
        
    # KUNCI KECEPATAN: Gunakan connection pooling bawaan (Tanpa NullPool)
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
        st.error(f"Gagal inisialisasi  users: {e}")

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
    st.markdown("<br><br>", unsafe_allow_html=True) 
    
    col_kiri, col_login, col_kanan = st.columns([1.2, 1.5, 1.2])
    
    with col_login:
        st.markdown("""
            <div style='text-align: center; margin-bottom: 20px;'>
                <h1 style='color: #1a64bc; font-weight: 900; margin-bottom: 0px; font-size: 32px; letter-spacing: -1px;'>DUKUH RAYA</h1>
                <p style='color: #64748b; font-size: 14px; margin-top: 5px; font-weight: 500;'>SILAKAN MASUK KE SISTEM MANAJEMEN</p>
            </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            login_user = st.text_input("👤 Username", placeholder="Masukkan username")
            login_pass = st.text_input("🔒 Password", type="password", placeholder="••••••••")
            
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            submit_login = st.form_submit_button("LOGIN DASHBOARD", use_container_width=True, type="primary")
            
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
        id, nama_perusahaan, nama_kapal, tahun, 
        kategori_pekerjaan, uraian_pekerjaan, 
        volume_satuan, harga_satuan
    FROM {NAMA_TABEL}
    ORDER BY nama_kapal, id
    """
    df = pd.read_sql(query, engine)
    
    # KITA JADIKAN STRING BIASA KARENA RAM SUDAH 8GB (ANTI-CRASH)
    for col in ['nama_perusahaan', 'nama_kapal', 'tahun', 'kategori_pekerjaan']:
        df[col] = df[col].fillna('-').astype(str)
        
    df['uraian_pekerjaan'] = df['uraian_pekerjaan'].fillna('-').astype(str)
    return df

# 🚀 FITUR BARU: Caching tabel Users (Mencegah Query SQL berulang-ulang saat navigasi)
@st.cache_data(ttl=60)
def load_users():
    with engine.connect() as conn:
        return pd.read_sql("SELECT id, username, role FROM users ORDER BY id", conn)

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"❌ Gagal mengambil data. Error: {e}")
    st.stop()

# --- SIDEBAR & FILTER DINAMIS ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/984/984233.png", width=120)

st.sidebar.markdown(f"👤 **Halo, {st.session_state['username']}** ({st.session_state['role']})")
if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state['logged_in'] = False
    st.session_state['username'] = ''
    st.session_state['role'] = ''
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 Filter Data")
search_query = st.sidebar.text_input("🔎 Cari Uraian...", placeholder="Contoh: Plat, Pipa...")

list_perusahaan = ["Semua"] + list(df_raw['nama_perusahaan'].dropna().unique())
filter_perusahaan = st.sidebar.selectbox("🏢 Klien / Pemilik", list_perusahaan)

# OPTIMASI MEMORI: Hapus .copy()
df_final = df_raw 

if filter_perusahaan != "Semua": df_final = df_final[df_final['nama_perusahaan'] == filter_perusahaan]
list_kapal = ["Semua"] + list(df_final['nama_kapal'].dropna().unique())
filter_kapal = st.sidebar.selectbox("⛴️ Nama Kapal", list_kapal)

list_tahun = ["Semua"] + list(df_raw['tahun'].dropna().unique())
filter_tahun = st.sidebar.selectbox("📅 Tahun", list_tahun)

if filter_kapal != "Semua": df_final = df_final[df_final['nama_kapal'] == filter_kapal]
if filter_tahun != "Semua": df_final = df_final[df_final['tahun'] == filter_tahun]

list_kategori = ["Semua"] + list(df_final['kategori_pekerjaan'].dropna().unique())
filter_kategori = st.sidebar.selectbox("🛠️ Kategori Pekerjaan", list_kategori)

if filter_kategori != "Semua": df_final = df_final[df_final['kategori_pekerjaan'] == filter_kategori]
if search_query: df_final = df_final[df_final['uraian_pekerjaan'].str.contains(search_query, case=False, na=False)]

# --- HEADER COMPACT ---
st.markdown("<h3 style='margin-bottom:15px; color:#1a64bc; line-height: 1.2;'>PT. DUKUH RAYA Shipyard<br>Docking Repair Pricing</h3>", unsafe_allow_html=True)

# --- MINI CARDS KPI ---
c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f'<div class="mini-card" style="border-left: 4px solid #1f77b4;"><p class="mc-title">📋 Total Item</p><p class="mc-val">{len(df_final)}</p></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="mini-card" style="border-left: 4px solid #28a745;"><p class="mc-title">🏢 Total Klien</p><p class="mc-val">{df_final["nama_perusahaan"].nunique()}</p></div>', unsafe_allow_html=True)
with c3: st.markdown(f'<div class="mini-card" style="border-left: 4px solid #ffc107;"><p class="mc-title">⛴️ Kapal</p><p class="mc-val">{df_final["nama_kapal"].nunique()}</p></div>', unsafe_allow_html=True)
with c4:
    thn_val = df_final["tahun"].nunique()
    st.markdown(f'<div class="mini-card" style="border-left: 4px solid #dc3545;"><p class="mc-title">📅 Tahun Referensi</p><p class="mc-val">{thn_val}</p></div>', unsafe_allow_html=True)

# --- TABEL & FORM AREA ---
df_tampil = df_final[['id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan']]
df_tampil = df_tampil.rename(columns={
    'id': 'ID Referensi', 'nama_perusahaan': 'Perusahaan', 'nama_kapal': 'Kapal', 
    'tahun': 'Tahun', 'kategori_pekerjaan': 'Kategori', 'uraian_pekerjaan': 'Uraian Pekerjaan', 
    'volume_satuan': 'Satuan', 'harga_satuan': 'Harga Satuan'
}).reset_index(drop=True)

# --- TABEL & FORM AREA ---
df_tampil = df_final[['id', 'nama_perusahaan', 'nama_kapal', 'tahun', 'kategori_pekerjaan', 'uraian_pekerjaan', 'volume_satuan', 'harga_satuan']]
df_tampil = df_tampil.rename(columns={
    'id': 'ID Referensi', 'nama_perusahaan': 'Perusahaan', 'nama_kapal': 'Kapal', 
    'tahun': 'Tahun', 'kategori_pekerjaan': 'Kategori', 'uraian_pekerjaan': 'Uraian Pekerjaan', 
    'volume_satuan': 'Satuan', 'harga_satuan': 'Harga Satuan'
}).reset_index(drop=True)

# 🚀 KEMBALI KE TABS: Mesin sudah stabil dan RAM besar
tabs_list = ["👁️ View Data", "➕ Tambah Data Baru", "✏️ Edit & Hapus"]
if st.session_state['role'] == 'admin':
    tabs_list.append("👥 Kelola Akses")

tabs = st.tabs(tabs_list)

with tabs[0]: 
    if df_tampil.empty:
        st.warning("⚠️ Data tidak ditemukan.")
    else:
        st.dataframe(
            df_tampil, 
            use_container_width=True, 
            hide_index=True, 
            height=650,
            column_config={
                "Harga Satuan": st.column_config.NumberColumn("Harga Satuan", format="Rp %d")
            }
        )

with tabs[1]: 
    st.markdown("### 📝 Formulir Penambahan Item Pekerjaan")
    with st.form("form_tambah_data", clear_on_submit=True):
        col_form1, col_form2 = st.columns(2)
        with col_form1:
            input_pt = st.text_input("🏢 Nama Klien / Perusahaan")
            input_kpl = st.text_input("⛴️ Nama Kapal")
            input_thn = st.text_input("📅 Tahun")
            input_kat = st.text_input("🛠️ Kategori Pekerjaan")
        with col_form2:
            input_urai = st.text_area("📝 Uraian Pekerjaan")
            input_sat = st.text_input("📏 Satuan (Volume)")
            input_hrg = st.number_input("💰 Harga Satuan (Rp)", min_value=0.0, step=1000.0)
            
        if st.form_submit_button("💾 Simpan Data Baru", type="primary", use_container_width=True):
            if not input_kpl or not input_thn or not input_urai:
                st.error("⚠️ Nama Kapal, Tahun, dan Uraian Pekerjaan WAJIB diisi!")
            else:
                slug = str(input_kpl).strip().replace(" ", "_").upper()
                prefix = f"{slug}-{str(input_thn).strip()}-"
                df_cek = df_raw[df_raw['id'].str.startswith(prefix, na=False)]
                
                try:
                    new_num = (int(df_cek['id'].max().split('-')[-1]) + 1) if not df_cek.empty else 1
                except:
                    new_num = len(df_cek) + 1
                    
                new_id = f"{prefix}{new_num:03d}"
                
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f"""
                            INSERT INTO {NAMA_TABEL} 
                            (id, nama_perusahaan, nama_kapal, tahun, kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan)
                            VALUES (:id, :pt, :kpl, :thn, :kat, :urai, :sat, :hrg)
                        """), {
                            "id": new_id, "pt": input_pt.upper(), "kpl": input_kpl.upper(), 
                            "thn": input_thn, "kat": input_kat, "urai": input_urai, 
                            "sat": input_sat, "hrg": input_hrg
                        })
                    st.cache_data.clear()
                    st.success(f"✅ Data berhasil disimpan! ID: **{new_id}**")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Gagal menyimpan data: {e}")

with tabs[2]: 
    st.info("💡 **Mode Edit:** Klik ganda pada teks untuk mengoreksi. **Untuk menghapus baris, centang kotak di kolom '❌ Hapus'.**")
    
    df_edit_view = df_tampil.copy()
    df_edit_view.insert(0, '❌ Hapus', False)
    
    edited_df = st.data_editor(
        df_edit_view, 
        num_rows="fixed", 
        use_container_width=True, 
        height=600, 
        hide_index=True, 
        key="tabel_editor",
        column_config={
            "Harga Satuan": st.column_config.NumberColumn("Harga Satuan", format="Rp %d")
        }
    )
    
    if st.button("💾 Simpan Perubahan Edit & Hapus", type="primary"):
        ids_to_delete = edited_df[edited_df['❌ Hapus'] == True]['ID Referensi'].tolist()
        
        changed_indices = []
        for i in range(len(df_tampil)):
            if df_tampil.iloc[i]['ID Referensi'] in ids_to_delete:
                continue 
            if not df_tampil.iloc[i].equals(edited_df.iloc[i].drop('❌ Hapus')):
                changed_indices.append(i)
                
        if not ids_to_delete and not changed_indices:
            st.warning("⚠️ Tidak ada perubahan atau penghapusan data yang terdeteksi.")
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
                            SET nama_perusahaan = :pt, nama_kapal = :kpl, tahun = :thn, 
                                kategori_pekerjaan = :kat, uraian_pekerjaan = :urai, 
                                volume_satuan = :sat, harga_satuan = :hrg
                            WHERE id = :id
                        """)
                        for idx in changed_indices:
                            row = edited_df.iloc[idx]
                            conn.execute(update_query, {
                                "pt": row['Perusahaan'], "kpl": row['Kapal'], "thn": row['Tahun'],
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

# --- TAB 4: KELOLA AKSES (HANYA ADMIN) ---
if st.session_state['role'] == 'admin':
    with tabs[3]:
        st.markdown("### 👥 Manajemen Pengguna")
        
        users_df = load_users()
            
        col_user1, col_user2 = st.columns([2, 1])
        
        with col_user1:
            st.markdown("#### Daftar Pengguna Aktif")
            st.dataframe(users_df, use_container_width=True, hide_index=True)
            
            st.markdown("#### Hapus Pengguna")
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
            st.markdown("#### Tambah Pengguna Baru")
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

            st.markdown("#### 🔑 Ubah Password")
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
                        except Exception as e:
                            st.error(f"❌ Gagal mengubah password: {e}")
