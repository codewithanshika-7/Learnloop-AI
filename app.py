import streamlit as st

# Page configuration
st.set_page_config(
    page_title="LearnLoop",
    page_icon="🎓",
    layout="centered"
)

# Title
st.title("🎓 LearnLoop")

st.subheader("Your syllabus. Your pace. Your learning path.")

st.write(
    "Create a personalized study roadmap based on your syllabus, "
    "exam date, available time, and current level."
)

st.divider()

# Student Information
st.header("📚 Tell us about your study goal")

# Syllabus
st.info("📄 Upload your syllabus to get started.")

syllabus = st.file_uploader(
    "Upload your syllabus",
    type=["pdf"]
)

# Exam date
exam_date = st.date_input(
    "📅 When is your exam?"
)

# Study hours
study_hours = st.number_input(
    "⏰ How many hours can you study daily?",
    min_value=1,
    max_value=12,
    value=2
)

# Current level
level = st.selectbox(
    "📊 What is your current level?",
    ["Beginner", "Intermediate", "Advanced"]
)

st.divider()

# Generate button
if st.button("🚀 Create My Learning Roadmap", use_container_width=True):

    if syllabus is None:
        st.warning("Please upload your syllabus first.")
    else:
        st.success("Great! Your personalized roadmap will be created here.")
