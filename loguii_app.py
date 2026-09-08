import sys
import re
import requests
import time
import os
import json
import base64
import math
from datetime import datetime
import streamlit as st
import pandas as pd
from PIL import Image
import pytesseract
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Tenta importar o leitor de PDF de forma segura
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# Configuração da Página
st.set_page_config(page_title="LoGuii - Rotas", layout="wide", page_icon="logo.png")

# Ajuste do Tesseract para Windows/Nuvem
if sys.platform.startswith('win'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Diretórios e Arquivos Locais
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
caminho_caricatura = os.path.join(diretorio_atual, "caricatura.png")
caminho_logo = os.path.join(diretorio_atual, "logo.png")
arquivo_historico = os.path.join(diretorio_atual, "historico_rotas.json")
arquivo_pendentes = os.path.join(diretorio_atual, "pendentes.json")

# --- LEITURA DO ARQUIVO DE ESTOQUE ---
@st.cache_data
def carregar_estoque():
    itens = []
    caminho_pdf_min = os.path.join(diretorio_atual, "estoque.pdf")
    caminho_pdf_mai = os.path.join(diretorio_atual, "estoque.PDF")
    
    caminho_correto = None
    if os.path.exists(caminho_pdf_min):
        caminho_correto = caminho_pdf_min
    elif os.path.exists(caminho_pdf_mai):
        caminho_correto = caminho_pdf_mai
    
    if caminho_correto and PyPDF2 is not None:
        try:
            with open(caminho_correto, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        for line in text.split('\n'):
                            line = line.strip()
                            match = re.search(r'^(\d{3,6})\s+(.+?)(?=\s+MARCA PADRAO|\s+MARCA\b|\s{2,})', line, re.IGNORECASE)
                            if match:
                                codigo = match.group(1).strip()
                                descricao = match.group(2).strip()
                                itens.append(f"{codigo} - {descricao}")
            if itens:
                return sorted(list(set(itens)))
        except Exception as e:
            st.sidebar.error(f"Erro ao ler arquivo de estoque: {e}")
            
    return ["Exemplo: Fita Adesiva - Cód 101", "Exemplo: Caixa Parda - Cód 102"]

lista_estoque = carregar_estoque()

# --- BANCO DE DADOS DE USUÁRIOS BLINDADO ---
USUARIOS_CADASTRADOS = {
    "admin": "123456",
    "expedicao": "loguii2026",
    "motorista": "uniaologuii"
}

if "autenticado" not in st.session_state: 
    st.session_state.autenticado = False

# --- TELA DE LOGIN ---
if not st.session_state.autenticado:
    col_vazia1, col_login, col_vazia2 = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(caminho_logo):
            st.image(caminho_logo, width=250)
        
        st.title("🔒 Acesso Restrito - LoGuii")
        st.markdown("Faça o login para acessar o sistema logístico.")
        
        user_login = st.text_input("Usuário")
        pass_login = st.text_input("Senha", type="password")
        
        if st.button("Entrar no Sistema", type="primary", use_container_width=True):
            usuario_limpo = user_login.strip().lower()
            
            if usuario_limpo in USUARIOS_CADASTRADOS and USUARIOS_CADASTRADOS[usuario_limpo] == pass_login:
                st.session_state.autenticado = True
                st.rerun() 
            else: 
                st.error("❌ Usuário ou senha incorretos. Verifique e tente novamente.")
    st.stop() 

# --- FUNÇÕES DE SALVAMENTO DOS PENDENTES ---
def salvar_pendentes(lista):
    with open(arquivo_pendentes, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=4)

def carregar_pendentes():
    if os.path.exists(arquivo_pendentes):
        try:
            with open(arquivo_pendentes, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

# --- FUNÇÃO DA MARCA D'ÁGUA ---
def aplicar_marca_dagua(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        css = f"""
        <style>
        [data-testid="stAppViewContainer"] > .main::before {{
            content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background-image: url("data:image/png;base64,{encoded_string}");
            background-size: 45%; background-position: center; background-repeat: no-repeat;
            background-attachment: fixed; opacity: 0.10; z-index: -1;
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)

aplicar_marca_dagua(caminho_caricatura)

# --- CABEÇALHO DA PÁGINA PRINCIPAL ---
col_texto, col_imagem = st.columns([5, 1])
with col_texto:
    st.title("🚚 LoGuii Solução Logística")
    st.markdown("Gerencie pedidos pendentes, agrupe por raio de 7km e gere rotas otimizadas.")
with col_imagem:
    if os.path.exists(caminho_caricatura):
        st.image(caminho_caricatura, width=130)

if "pendentes" not in st.session_state:
    st.session_state.pendentes = carregar_pendentes()

# --- INTELIGÊNCIA GEOGRÁFICA (HAVERSINE & AGRUPAMENTO 7KM) ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def geocodificar(endereco):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {'User-Agent': 'LoGuiiApp/1.0'}
    params = {'q': endereco, 'format': 'json', 'limit': 1}
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.json(): return res.json()[0]['lat'], res.json()[0]['lon']
    except: pass
    if "," in endereco:
        rua = endereco.split(",")[0].strip()
        if "Franca" not in rua: rua = f"{rua}, Franca, SP, Brasil"
        try:
            res = requests.get(url, headers=headers, params={'q': rua, 'format': 'json', 'limit': 1})
            if res.json(): return res.json()[0]['lat'], res.json()[0]['lon']
        except: pass
    return None, None

def atualizar_agrupamentos(pendentes):
    n = len(pendentes)
    if n == 0: return

    for p in pendentes:
        if not p.get('lat') or not p.get('lon'):
            lat, lon = geocodificar(f"{p['endereco']}, Franca - SP, Brasil")
            if lat and lon:
                p['lat'], p['lon'] = lat, lon
            time.sleep(0.5)

    adj = {i: [] for i in range(n)}
    for i in range(n):
        for j in range(i+1, n):
            if pendentes[i].get('lat') and pendentes[j].get('lat'):
                d = haversine(float(pendentes[i]['lat']), float(pendentes[i]['lon']), float(pendentes[j]['lat']), float(pendentes[j]['lon']))
                if d <= 7.0:
                    adj[i].append(j)
                    adj[j].append(i)
    
    visited = set()
    grupo_id = 1
    for i in range(n):
        if i not in visited:
            queue = [i]
            visited.add(i)
            componente = [i]
            
            while queue:
                curr = queue.pop(0)
                for viz in adj[curr]:
                    if viz not in visited:
                        visited.add(viz)
                        queue.append(viz)
                        componente.append(viz)
            
            nome_grupo = None
            for c in componente:
                if pendentes[c].get('fixo') and pendentes[c].get('grupo'):
                    nome_grupo = pendentes[c]['grupo']
                    break
            
            if not nome_grupo:
                nome_grupo = f"Rota {grupo_id}"
                grupo_id += 1
                
            for c in componente:
                if not pendentes[c].get('fixo'):
                    pendentes[c]['grupo'] = nome_grupo

# --- PLANILHA DE CLIENTES ---
@st.cache_data
def carregar_clientes():
    arquivos = [
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xlsx"),
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xls"),
        os.path.join(diretorio_atual, "clientes.xlsx"),
        "Listagem_Clientes_de_Franca.xlsx"
    ]
    for arquivo in arquivos:
        if os.path.exists(arquivo):
            try:
                df = pd.read_excel(arquivo)
                df.columns = df.columns.str.strip()
                if 'Código' in df.columns:
                    df['Código'] = df['Código'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                if 'Numero' in df.columns:
                    df['Numero'] = df['Numero'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                return df, True, arquivo
            except Exception as e:
                return pd.DataFrame(), False, f"Erro: {str(e)}"
    return pd.DataFrame(), False, "Planilha não encontrada."

df_clientes, status_ok, msg_erro = carregar_clientes()

# --- MENU LATERAL (SIDEBAR) ---
if os.path.exists(caminho_logo):
    st.sidebar.image(caminho_logo, use_container_width=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True) 

st.sidebar.header("🔍 1. Adicionar à Fila")
if status_ok and not df_clientes.empty:
    colunas_necessarias = ['Código', 'Cliente', 'Endereco', 'Numero']
    if all(col in df_clientes.columns for col in colunas_necessarias):
        opcoes = df_clientes['Código'] + " - " + df_clientes['Cliente']
        cliente_selecionado = st.sidebar.selectbox("Digite o Código ou Nome do Cliente:", options=["Selecione..."] + opcoes.tolist())
        if st.sidebar.button("➕ Enviar para Pendentes", type="primary"):
            if cliente_selecionado != "Selecione...":
                with st.spinner("Localizando no mapa e agrupando..."):
                    codigo_busca = cliente_selecionado.split(" - ")[0]
                    dados_cli = df_clientes[df_clientes['Código'] == codigo_busca].iloc[0]
                    rua = str(dados_cli['Endereco']).strip().split('-')[0].strip()
                    num = str(dados_cli['Numero']).strip()
                    endereco_completo = f"{rua}, {num}" if num.lower() != 'nan' and num else rua
                    
                    st.session_state.pendentes.append({
                        "uid": f"bd_{codigo_busca}_{time.time()}",
                        "cliente": str(dados_cli['Cliente']),
                        "endereco": endereco_completo,
                        "pedido_num": "", "urgente": False, "horario": "",
                        "selecionado": True, "itens": [], "grupo": "Calculando...", "fixo": False
                    })
                    atualizar_agrupamentos(st.session_state.pendentes)
                    salvar_pendentes(st.session_state.pendentes)
                    st.sidebar.success(f"{dados_cli['Cliente']} adicionado!")
                    st.rerun()
            else:
                st.sidebar.warning("Selecione um cliente primeiro.")
else:
    st.sidebar.error("Planilha de clientes não encontrada!")

st.sidebar.divider()

st.sidebar.header("📁 2. Adicionar por Imagem")
modo_imagem = st.sidebar.radio("Como deseja enviar a imagem?", ["Fazer Upload", "Tirar Foto"])
imagens_para_processar = []
if modo_imagem == "Fazer Upload":
    uploaded_files = st.sidebar.file_uploader("Envie a imagem", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if uploaded_files:
        imagens_para_processar.extend(uploaded_files)
else:
    foto_camera = st.sidebar.camera_input("📸 Tire a foto")
    if foto_camera:
        imagens_para_processar.append(foto_camera)

def extrair_dados_imagem(imagem):
    texto = pytesseract.image_to_string(imagem, lang="por")
    texto_cliente = texto[texto.find("Cliente:"):] if "Cliente:" in texto else texto[texto.find("CNPJ/CPF:"):] if "CNPJ/CPF:" in texto else texto
    cliente_match = re.search(r"Cliente:\s*\d+\s*-\s*(.*?)(?:-|\n)", texto, re.IGNORECASE) or re.search(r"Cliente:\s*(.*)", texto, re.IGNORECASE)
    cliente = cliente_match.group(1).strip() if cliente_match else "Não identificado"
    linha_endereco_match = re.search(r"Endereço:\s*([^\n]*)", texto_cliente, re.IGNORECASE)
    rua, numero = "", ""
    if linha_endereco_match:
        linha = linha_endereco_match.group(1)
        rua = re.split(r'\s*-\s*NULL|\s*N[°ºoOwW]|\s*w[°º]|\s*CEP', linha, flags=re.IGNORECASE)[0].strip().split('-')[0].strip()
        rua = re.sub(r'[\-,\.\s]+$', '', rua)
        numero_match = re.search(r"(?:N[°ºoOwW\.\*]|\bw[°º]|N\b|- w[°º])\s*(\d+)", linha, re.IGNORECASE) or re.search(r"(\d+)\s*CEP", linha, re.IGNORECASE)
        numero = numero_match.group(1).strip() if numero_match else ""
    return {"cliente": cliente, "endereco": f"{rua}, {numero}" if (rua and numero) else rua if rua else "Endereço não identificado", "pedido_num": "", "urgente": False, "horario": "", "selecionado": True, "itens": [], "grupo": "Calculando...", "fixo": False}

if imagens_para_processar:
    with st.spinner("Lendo imagens e agrupando pelo mapa..."):
        for arq_imagem in imagens_para_processar:
            image = Image.open(arq_imagem)
            file_id = getattr(arq_imagem, "name", f"camera_{time.time()}")
            if not any(p.get("uid") == file_id for p in st.session_state.pendentes):
                dados = extrair_dados_imagem(image)
                dados["uid"] = file_id
                st.session_state.pendentes.append(dados)
        atualizar_agrupamentos(st.session_state.pendentes)
        salvar_pendentes(st.session_state.pendentes)
        st.rerun()

st.sidebar.divider()
if st.sidebar.button("🚪 Sair do Sistema (Logout)"):
    st.session_state.autenticado = False
    st.rerun()

# --- LISTAGEM DE PENDENTES ---
st.subheader("📋 Fila de Pedidos Pendentes")
st.markdown("Pedidos distantes até 7km são agrupados automaticamente. Digite um nome no campo Grupo para fixá-lo manualmente.")

st.session_state.pendentes.sort(key=lambda x: (x.get('grupo', ''), not x.get('urgente', False)))

if st.session_state.pendentes:
    c_sel, c_grp, c_cli, c_end, c_ped, c_hor, c_bell, c_del = st.columns([0.5, 1.5, 2.5, 3, 1.5, 1, 0.5, 0.5])
    c_grp.markdown("**Grupo (7km)**")
    c_cli.markdown("**Cliente**")
    c_end.markdown("**Endereço**")
    c_ped.markdown("**Nº Ped.**")
    c_hor.markdown("**Horário**")
    st.divider()

    for i, p in enumerate(st.session_state.pendentes):
        col_sel, col_grp, col_cli, col_end, col_ped, col_hor, col_bell, col_del = st.columns([0.5, 1.5, 2.5, 3, 1.5, 1, 0.5, 0.5])
        
        p['selecionado'] = col_sel.checkbox("", value=p.get('selecionado', True), key=f"sel_{p['uid']}")
        
        novo_grupo = col_grp.text_input("Grupo", value=p.get('grupo', ''), key=f"grp_{p['uid']}", label_visibility="collapsed")
        if novo_grupo != p.get('grupo', ''):
            p['grupo'] = novo_grupo
            p['fixo'] = True
            salvar_pendentes(st.session_state.pendentes)
        
        p['cliente'] = col_cli.text_input("Cliente:", value=p['cliente'], key=f"cli_{p['uid']}", label_visibility="collapsed")
        p['endereco'] = col_end.text_input("Endereço:", value=p['endereco'], key=f"end_{p['uid']}", label_visibility="collapsed")
        p['pedido_num'] = col_ped.text_input("Pedido:", value=p.get('pedido_num', ''), key=f"ped_{p['uid']}", label_visibility="collapsed")
        
        if p.get('urgente', False):
            p['horario'] = col_hor.text_input("Horário:", value=p.get('horario', ''), key=f"hor_{p['uid']}", placeholder="14h00", label_visibility="collapsed")
        else:
            col_hor.write("")

        btn_sino = "🔔" if p.get('urgente', False) else "🔕"
        if col_bell.button(btn_sino, key=f"urg_{p['uid']}", help="Marcar/Desmarcar Urgência"):
            p['urgente'] = not p.get('urgente', False)
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()

        if col_del.button("🗑️", key=f"del_{p['uid']}"):
            st.session_state.pendentes.pop(i)
            atualizar_agrupamentos(st.session_state.pendentes)
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()
            
        _, col_itens = st.columns([0.5, 9.5])
        with col_itens:
            p['itens'] = st.multiselect("📦 Itens do Pedido (Pesquise por nome ou código):", options=lista_estoque, default=p.get('itens', []), key=f"itens_{p['uid']}")

        st.divider()

    col_btn1, col_btn2 = st.columns([2, 2])
    with col_btn1:
        if st.button("🗑️ Limpar Toda a Fila de Pendentes"):
            st.session_state.pendentes = []
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()
    with col_btn2:
        if st.button("🔄 Forçar Re-agrupamento (Limpa Nomes Manuais)"):
            for p in st.session_state.pendentes:
                p['fixo'] = False
            atualizar_agrupamentos(st.session_state.pendentes)
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()
else:
    st.info("A fila está vazia. Adicione pedidos usando o menu lateral.")

salvar_pendentes(st.session_state.pendentes)

# --- ROTINAS DE IMPRESSÃO E MAPA ---
def gerar_pdf(ordem_entregas, nome_motorista):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    if os.path.exists(caminho_logo):
        c.drawImage(caminho_logo, 40, altura - 80, width=120, height=45, preserveAspectRatio=True, mask='auto')
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, altura - 50, "LoGuii Solução Logística")
    c.setFont("Helvetica", 10)
    c.drawString(180, altura - 65, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    if nome_motorista:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(180, altura - 85, f"Motorista: {nome_motorista}")
        
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, altura - 115, "Ponto de Partida:")
    c.setFont("Helvetica", 12)
    c.drawString(50, altura - 130, "Rua Doutor Ivom Rodrigues Pereira, 5078")
    c.line(50, altura - 145, largura - 50, altura - 145)
    
    y = altura - 175
    
    for idx, p in enumerate(ordem_entregas):
        if y < 100:
            c.showPage()
            y = altura - 50
            
        prefixo = f"[URGENTE {p.get('horario', '')}] " if p.get('urgente') else ""
        num_pedido_str = f" | Pedido: {p.get('pedido_num')}" if p.get('pedido_num') else ""
        
        if p.get('urgente'):
            c.setFillColorRGB(0.8, 0, 0)
            
        c.setFont("Helvetica-Bold", 12)
        
        c.drawString(50, y, f"[{idx+1}] {prefixo}Cliente: {p['cliente']}{num_pedido_str}")
        c.setFillColorRGB(0, 0, 0) 
        c.rect(largura - 70, y - 10, 15, 15)
        y -= 15
        
        c.setFont("Helvetica", 11)
        c.drawString(50, y, f"Endereço: {p['endereco']}")
        y -= 15
        
        if p.get('itens'):
            y -= 5
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, "Itens a Carregar:")
            y -= 15
            c.setFont("Helvetica", 10)
            for item in p['itens']:
                if y < 50:
                    c.showPage()
                    y = altura - 50
                c.rect(50, y, 10, 10) 
                c.drawString(65, y + 2, item[:85] + "..." if len(item) > 85 else item)
                y -= 15
        y -= 5
        c.line(50, y, largura - 50, y)
        y -= 25
        
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "📍 RETORNO: Base União Embalagens")
    y -= 15
    c.setFont("Helvetica", 11)
    c.drawString(50, y, "Endereço: Rua Doutor Ivom Rodrigues Pereira, 5078")
    c.save()
    buffer.seek(0)
    return buffer

def extrair_minutos(horario_str):
    if not horario_str: return 720
    try:
        numeros = re.findall(r'\d+', str(horario_str))
        if len(numeros) >= 2: return int(numeros[0]) * 60 + int(numeros[1])
        elif len(numeros) == 1:
            n = numeros[0]
            if len(n) >= 3: return int(n[:-2]) * 60 + int(n[-2:])
            return int(n) * 60
    except: pass
    return 720

def otimizar_rota_com_urgencia(origem_lat, origem_lon, pedidos):
    unvisited = pedidos.copy()
    current_lat, current_lon = float(origem_lat), float(origem_lon)
    rota_ordenada = []
    while unvisited:
        best_score = float('inf')
        best_idx = -1
        for i, p in enumerate(unvisited):
            dist = haversine(current_lat, current_lon, float(p['lat']), float(p['lon']))
            bonus = 12 + 6 * (1 - (extrair_minutos(p.get('horario', '')) / 1440)) if p.get('urgente') else 0
            if (dist - bonus) < best_score:
                best_score = (dist - bonus)
                best_idx = i
        next_p = unvisited.pop(best_idx)
        rota_ordenada.append(next_p)
        current_lat, current_lon = float(next_p['lat']), float(next_p['lon'])
    return rota_ordenada

# --- OTIMIZAÇÃO E GERAÇÃO DA ROTA ---
st.subheader("🗺️ Otimização e Impressão")
nome_motorista = st.text_input("👨‍✈️ Nome do Motorista (Opcional):", placeholder="Ex: Roberto")
pedidos_selecionados = [p for p in st.session_state.pendentes if p.get('selecionado', True)]

if st.button("🗺️ Gerar Rota Otimizada", type="primary"):
    if not pedidos_selecionados:
        st.warning("Selecione pelo menos um endereço na fila para gerar a rota.")
    else:
        with st.spinner("Calculando rotas otimizadas com inteligência de urgência..."):
            lat_o, lon_o = geocodificar("Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP, Brasil")
            if not (lat_o and lon_o):
                st.error("Erro ao localizar endereço base.")
            else:
                enderecos_validos = [p for p in pedidos_selecionados if p.get('lat') and p.get('lon')]
                if enderecos_validos:
                    ordem_entregas = otimizar_rota_com_urgencia(lat_o, lon_o, enderecos_validos)
                    st.success("Rota gerada com sucesso!")
                    st.subheader("📍 Ordem Sugerida de Entregas")
                    
                    for idx, p in enumerate(ordem_entregas):
                        urg_text = f" **[URG. {p.get('horario', '')}]** " if p.get('urgente') else ""
                        st.markdown(f"**Parada {idx+1}:** {urg_text}{p['cliente']} — *{p['endereco']}*")
                    
                    origem_link = "Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP".replace(" ", "+")
                    pontos = "|".join([f"{p['endereco']}, Franca, SP".replace(" ", "+") for p in ordem_entregas])
                    link_maps = f"https://www.google.com/maps/dir/?api=1&origin={origem_link}&destination={origem_link}&waypoints={pontos}"
                    
                    st.markdown(f"[🔗 Abrir Rota no Google Maps]({link_maps})", unsafe_allow_html=True)
                    
                    st.divider()
                    pdf_arquivo = gerar_pdf(ordem_entregas, nome_motorista)
                    nome_arquivo = f"LoGuii_Rota_{datetime.now().strftime('%d%m%Y_%H%M')}.pdf"
                    
                    st.download_button(label="📄 Baixar PDF com Checklist da Rota", data=pdf_arquivo, file_name=nome_arquivo, mime="application/pdf", type="primary")
                    
                    st.session_state.pendentes = [p for p in st.session_state.pendentes if not p.get('selecionado', False)]
                    salvar_pendentes(st.session_state.pendentes)
                    
                    historico = []
                    if os.path.exists(arquivo_historico):
                        try:
                            with open(arquivo_historico, "r", encoding="utf-8") as f:
                                historico = json.load(f)
                        except:
                            pass
                    
                    historico = [r for r in historico if (time.time() - r.get("timestamp", 0)) <= 172800]
                    
                    historico.insert(0, {
                        "timestamp": time.time(), 
                        "data_formatada": datetime.now().strftime("%d/%m/%Y %H:%M"), 
                        "motorista": nome_motorista or "Não informado", 
                        "entregas": ordem_entregas, 
                        "link_maps": link_maps,
                        "link_rastreamento": "" 
                    })
                    
                    with open(arquivo_historico, "w", encoding="utf-8") as f:
                        json.dump(historico, f, ensure_ascii=False, indent=4)
                else:
                    st.error("Não foram encontrados endereços válidos para criar a rota.")

# --- HISTÓRICO DE ROTAS E RASTREAMENTO AO VIVO ---
st.divider()
st.subheader("🕒 Histórico de Rotas e Rastreamento (Últimas 48h)")
hist = []
if os.path.exists(arquivo_historico):
    try:
        with open(arquivo_historico, "r", encoding="utf-8") as f:
            hist = json.load(f)
    except:
        pass
        
hist = [r for r in hist if (time.time() - r.get("timestamp", 0)) <= 172800]

if hist:
    for i, rota in enumerate(hist):
        with st.expander(f"🛣️ Rota de {rota['data_formatada']} - Motorista: {rota['motorista']} ({len(rota['entregas'])} entregas)"):
            
            st.markdown("---")
            st.markdown("**📡 Rastreamento em Tempo Real**")
            col_link, col_btn_rastreio = st.columns([4, 2])
            
            link_atual = rota.get('link_rastreamento', '')
            with col_link:
                novo_link = st.text_input("Cole o link do Maps ou WhatsApp aqui:", value=link_atual, key=f"link_rastreio_{i}", label_visibility="collapsed", placeholder="Cole o link de rastreamento ao vivo aqui...")
            
            with col_btn_rastreio:
                if novo_link != link_atual:
                    hist[i]['link_rastreamento'] = novo_link
                    with open(arquivo_historico, "w", encoding="utf-8") as f:
                        json.dump(hist, f, ensure_ascii=False, indent=4)
                    st.rerun()
                if novo_link:
                    st.markdown(f"<a href='{novo_link}' target='_blank'><button style='width:100%; background-color:#2e7b32; color:white; border:none; padding:6px; border-radius:5px; cursor:pointer;'>📍 Acompanhar Agora</button></a>", unsafe_allow_html=True)
            st.markdown("---")
            
            st.markdown(f"[🔗 Abrir Rota no Google Maps]({rota['link_maps']})", unsafe_allow_html=True)
            for p in rota['entregas']:
                urg_text = f" **[URG. {p.get('horario', '')}]**" if p.get('urgente') else ""
                st.write(f"-{urg_text} {p['cliente']}: *{p['endereco']}*")
                
                if p.get('itens'):
                    for item in p['itens']:
                        st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;📦 {item}")
            
            col_b1, col_b2, col_b3 = st.columns([2, 2, 2])
            with col_b1:
                st.download_button(label="📄 Re-imprimir PDF", data=gerar_pdf(rota['entregas'], rota['motorista']), file_name=f"LoGuii_Hist_{i}.pdf", mime="application/pdf", key=f"dl_hist_{i}")
            with col_b2:
                if st.button("✏️ Editar (Devolver p/ Fila)", key=f"edit_hist_{i}"):
                    for p_hist in rota['entregas']:
                        p_hist['uid'] = f"hist_{time.time()}_{p_hist['cliente']}"
                        p_hist['selecionado'] = True
                        p_hist['fixo'] = False
                        st.session_state.pendentes.append(p_hist)
                    atualizar_agrupamentos(st.session_state.pendentes)
                    salvar_pendentes(st.session_state.pendentes)
                    hist.pop(i)
                    with open(arquivo_historico, "w", encoding="utf-8") as f:
                        json.dump(hist, f, ensure_ascii=False, indent=4)
                    st.rerun()
            with col_b3:
                if st.button("🗑️ Excluir Rota", key=f"del_hist_{i}", type="secondary"):
                    hist.pop(i)
                    with open(arquivo_historico, "w", encoding="utf-8") as f:
                        json.dump(hist, f, ensure_ascii=False, indent=4)
                    st.rerun()
else:
    st.info("Nenhuma rota salva ainda.")
