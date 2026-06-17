import streamlit as st
from harmonai_pipeline import run_harmonai_pipeline_async

st.set_page_config(page_title="HarmonAI", page_icon="🎵", layout="centered")

st.title("🎵 HarmonAI")
st.markdown("Şarkının müzikal armoni analizini yapay zeka ile çıkar.")

# --- Kullanıcı girdileri ---
youtube_url = st.text_input("YouTube Linki", placeholder="https://www.youtube.com/watch?v=...")
artist_name = st.text_input("Sanatçı Adı", placeholder="örn. Radiohead")
song_title  = st.text_input("Şarkı Adı",   placeholder="örn. Creep")

# --- Analiz butonu ---
if st.button("🎼 Analiz Et", use_container_width=True):

    if not youtube_url or not artist_name or not song_title:
        st.warning("Lütfen tüm alanları doldur.")
    else:
        with st.spinner("Analiz yapılıyor... Bu işlem 2-3 dakika sürebilir."):
            sonuc = run_harmonai_pipeline_async(youtube_url, artist_name, song_title)

        if sonuc is None:
            st.error("Analiz başarısız oldu. YouTube linkini veya şarkı adını kontrol et.")
        else:
            # --- Sonuçları göster ---
            st.success("Analiz tamamlandı!")

            col1, col2, col3 = st.columns(3)
            col1.metric("Ton", f"{sonuc['detected_key']} {sonuc['detected_mode']}")
            col2.metric("Tempo", f"{int(sonuc['tempo'])} BPM")
            col3.metric("Akor Sayısı", len(sonuc['final_chords']))

            st.markdown("### 🎸 Tespit Edilen Akorlar")
            st.write(" · ".join(sonuc['final_chords']))

            if sonuc['web_chords'].get('success'):
                st.markdown("### 🌐 Web'den Çekilen Akorlar")
                st.write(" · ".join(sonuc['web_chords']['unique_chords']))

            st.markdown("### 📝 HarmonAI Raporu")
            st.markdown(sonuc['final_report'])