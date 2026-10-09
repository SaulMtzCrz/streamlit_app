import streamlit as st
from auth import AuthManager
from login_page import LoginPage, LoginRegisterPage
from streamlitapp import MainDashboardPage

class MultiPageApp:

    def __init__(self):
        st.set_page_config(
            page_title="Gestor de compras",
            layout="wide"
        )
        # Inicializa las variables de estado de sesión
        AuthManager.init_session()

    def run(self):
        if st.session_state["registering"]:
            LoginRegisterPage().render()
        elif not st.session_state["authenticated"]:
            LoginPage().render()
        else:
            MainDashboardPage().render()

if __name__ == "__main__":
    app = MultiPageApp()
    app.run()