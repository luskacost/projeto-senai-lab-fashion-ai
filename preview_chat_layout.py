# Script manual de preview visual do layout de chat -- rode com `streamlit run preview_chat_layout.py`.
# Nao faz parte da suite automatizada de testes (tests/); renomeado de test_chat_layout.py
# para nao ser confundido com um teste unittest nem coletado pelo unittest discover.
import streamlit as st

st.set_page_config(page_title="Test Chat Layout", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "user", "content": "Olá!"},
        {"role": "assistant", "content": "Olá, como posso ajudar com moda hoje?"}
    ]

tab1, tab2 = st.tabs(["💬 Assistente", "⚙️ Configurações"])

with tab1:
    st.title("Teste de Layout de Chat")
    
    # Container para mensagens acima do input
    chat_container = st.container()
    
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    prompt = st.chat_input("Digite sua mensagem...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.messages.append({"role": "assistant", "content": f"Resposta para: {prompt}"})
        st.rerun()

with tab2:
    st.write("Configurações")
