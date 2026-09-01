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

import sys

# Apontando o caminho do leitor de imagens:
# Se for Windows (seu PC), usa o caminho do disco C:
if sys.platform.startswith('win'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# Se for Linux (Nuvem do Streamlit), o sistema já sabe onde achar, então não precisa de caminho!

# Configuração da Página
st.set_page_config(page_title="LoGuii - Rotas", layout="wide", page_icon="logo.png")

# Descobre a pasta atual do arquivo
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
caminho_caricatura = os.path.join(diretorio_atual, "caricatura.png")
caminho_logo = os.path.join(diretorio_atual, "logo.png")
arquivo_historico = os.path.join(diretorio_atual, "historico_rotas.json")
arquivo_pendentes = os.path.join(diretorio_atual, "pendentes.json")

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
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: url("data:image/png;base64,{encoded_string}");
            background-size: 45%; 
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
            opacity: 0.10; 
            z-index: -1;
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)

aplicar_marca_dagua(caminho_caricatura)

# --- CABEÇALHO COM A CARICATURA NO TOPO DIREITO ---
col_texto, col_imagem = st.columns([5, 1])

with col_texto:
    st.title("🚚 LoGuii Solução Logística")
    st.markdown("Gerencie pedidos pendentes, defina urgências e gere rotas otimizadas com retorno à base.")

with col_imagem:
    if os.path.exists(caminho_caricatura):
        st.image(caminho_caricatura, width=130)

# Inicializar a FILA DE PENDENTES com os dados salvos
if "pendentes" not in st.session_state:
    st.session_state.pendentes = carregar_pendentes()

# --- FUNÇÃO PARA CARREGAR PLANILHA DE CLIENTES ---
@st.cache_data
def carregar_clientes():
    arquivos_possiveis = [
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xlsx"),
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xls"),
        os.path.join(diretorio_atual, "clientes.xlsx"),
        "Listagem_Clientes_de_Franca.xlsx" 
    ]
    
    for arquivo in arquivos_possiveis:
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
                return pd.DataFrame(), False, f"Arquivo encontrado, mas deu erro na leitura: {str(e)}"
                
    return pd.DataFrame(), False, "O sistema não encontrou a planilha na mesma pasta do arquivo app.py."

df_clientes, status_ok, msg_erro = carregar_clientes()

# --- FUNÇÃO DO HISTÓRICO ---
def gerenciar_historico(acao='listar', dados=None, idx=None):
    historico = []
    if os.path.exists(arquivo_historico):
        try:
            with open(arquivo_historico, "r", encoding="utf-8") as f:
                historico = json.load(f)
        except:
            pass
    
    tempo_atual = time.time()
    historico = [r for r in historico if (tempo_atual - r.get("timestamp", 0)) <= 172800]
    
    if acao == 'adicionar' and dados:
        historico.insert(0, dados)
        with open(arquivo_historico, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=4)
            
    elif acao == 'excluir' and idx is not None:
        if 0 <= idx < len(historico):
            historico.pop(idx)
            with open(arquivo_historico, "w", encoding="utf-8") as f:
                json.dump(historico, f, ensure_ascii=False, indent=4)
                
    return historico

# --- INTELIGÊNCIA DE ORDENAÇÃO DE URGÊNCIA ---
def haversine(lat1, lon1, lat2, lon2):
    """Calcula a distância em Km entre dois pontos no globo."""
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def extrair_minutos(horario_str):
    """Lê o horário (ex: 14h, 10:30) e converte para minutos do dia."""
    if not horario_str: return 720 # Padrão 12h
    try:
        numeros = re.findall(r'\d+', str(horario_str))
        if len(numeros) >= 2:
            return int(numeros[0]) * 60 + int(numeros[1])
        elif len(numeros) == 1:
            n = numeros[0]
            if len(n) >= 3:
                return int(n[:-2]) * 60 + int(n[-2:])
            return int(n) * 60
    except:
        pass
    return 720

def otimizar_rota_com_urgencia(origem_lat, origem_lon, pedidos):
    """Algoritmo de Roteirização Guloso que respeita as urgências e horários."""
    unvisited = pedidos.copy()
    current_lat, current_lon = float(origem_lat), float(origem_lon)
    rota_ordenada = []
    
    while unvisited:
        best_score = float('inf')
        best_idx = -1
        
        for i, p in enumerate(unvisited):
            dist = haversine(current_lat, current_lon, float(p['lat']), float(p['lon']))
            
            bonus = 0
            if p.get('urgente'):
                minutos = extrair_minutos(p.get('horario', ''))
                # Bônus de Urgência: Reduz a distância 'falsa' para o algoritmo puxar essa entrega primeiro
                # Entregas mais cedo ganham bônus ainda maior (até 18km de vantagem).
                bonus = 12 + 6 * (1 - (minutos / 1440))
                
            score = dist - bonus
            
            if score < best_score:
                best_score = score
                best_idx = i
                
        next_p = unvisited.pop(best_idx)
        rota_ordenada.append(next_p)
        current_lat = float(next_p['lat'])
        current_lon = float(next_p['lon'])
        
    return rota_ordenada

# --- LOGO DA EMPRESA NA BARRA LATERAL ---
if os.path.exists(caminho_logo):
    st.sidebar.image(caminho_logo, use_container_width=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True) 

# --- BARRA LATERAL: OPÇÕES DE ADIÇÃO ---
st.sidebar.header("🔍 1. Adicionar à Fila")

if status_ok and not df_clientes.empty:
    colunas_necessarias = ['Código', 'Cliente', 'Endereco', 'Numero']
    
    if all(col in df_clientes.columns for col in colunas_necessarias):
        opcoes = df_clientes['Código'] + " - " + df_clientes['Cliente']
        cliente_selecionado = st.sidebar.selectbox("Digite o Código ou Nome do Cliente:", options=["Selecione..."] + opcoes.tolist())
        
        if st.sidebar.button("➕ Enviar para Pendentes", type="primary"):
            if cliente_selecionado != "Selecione...":
                codigo_busca = cliente_selecionado.split(" - ")[0]
                dados_cli = df_clientes[df_clientes['Código'] == codigo_busca].iloc[0]
                
                rua_bruta = str(dados_cli['Endereco']).strip()
                rua_limpa = rua_bruta.split('-')[0].strip()
                num = str(dados_cli['Numero']).strip()
                if num.lower() == 'nan': num = ""
                    
                endereco_completo = f"{rua_limpa}, {num}" if num else rua_limpa
                
                st.session_state.pendentes.append({
                    "uid": f"bd_{codigo_busca}_{time.time()}",
                    "cliente": str(dados_cli['Cliente']),
                    "endereco": endereco_completo,
                    "pedido_num": "",
                    "urgente": False,
                    "horario": "",
                    "selecionado": True
                })
                salvar_pendentes(st.session_state.pendentes)
                st.sidebar.success(f"{dados_cli['Cliente']} adicionado à fila!")
            else:
                st.sidebar.warning("Selecione um cliente primeiro.")
    else:
        st.sidebar.error("A planilha foi encontrada, mas o nome de alguma coluna está incorreto.")
else:
    st.sidebar.error("Planilha de clientes não encontrada!")

st.sidebar.divider()

st.sidebar.header("📁 2. Adicionar por Imagem")
modo_imagem = st.sidebar.radio("Como deseja enviar a imagem?", ["Fazer Upload", "Tirar Foto"])
imagens_para_processar = []

if modo_imagem == "Fazer Upload":
    uploaded_files = st.sidebar.file_uploader("Envie a imagem do pedido", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if uploaded_files: imagens_para_processar.extend(uploaded_files)
else:
    foto_camera = st.sidebar.camera_input("📸 Tire a foto do comprovante")
    if foto_camera: imagens_para_processar.append(foto_camera)

def extrair_dados_imagem(imagem):
    texto = pytesseract.image_to_string(imagem, lang="por")
    texto_cliente = texto
    if "Cliente:" in texto: texto_cliente = texto[texto.find("Cliente:"):]
    elif "CNPJ/CPF:" in texto: texto_cliente = texto[texto.find("CNPJ/CPF:"):]

    cliente_match = re.search(r"Cliente:\s*\d+\s*-\s*(.*?)(?:-|\n)", texto, re.IGNORECASE)
    if not cliente_match: cliente_match = re.search(r"Cliente:\s*(.*)", texto, re.IGNORECASE)
    cliente = cliente_match.group(1).strip() if cliente_match else "Não identificado"

    linha_endereco_match = re.search(r"Endereço:\s*([^\n]*)", texto_cliente, re.IGNORECASE)
    rua, numero = "", ""
    if linha_endereco_match:
        linha = linha_endereco_match.group(1)
        partes = re.split(r'\s*-\s*NULL|\s*N[°ºoOwW]|\s*w[°º]|\s*CEP', linha, flags=re.IGNORECASE)
        rua = partes[0].strip().split('-')[0].strip()
        rua = re.sub(r'[\-,\.\s]+$', '', rua)
        numero_match = re.search(r"(?:N[°ºoOwW\.\*]|\bw[°º]|N\b|- w[°º])\s*(\d+)", linha, re.IGNORECASE)
        if not numero_match: numero_match = re.search(r"(\d+)\s*CEP", linha, re.IGNORECASE)
        numero = numero_match.group(1).strip() if numero_match else ""

    endereco_completo = f"{rua}, {numero}" if (rua and numero) else rua if rua else "Endereço não identificado"
    return {"cliente": cliente, "endereco": endereco_completo, "pedido_num": "", "urgente": False, "horario": "", "selecionado": True}

def geocodificar(endereco):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {'User-Agent': 'LoGuiiApp/1.0'}
    params = {'q': endereco, 'format': 'json', 'limit': 1}
    try:
        res = requests.get(url, headers=headers, params=params)
        dados = res.json()
        if dados: return dados[0]['lat'], dados[0]['lon']
    except: pass
    
    if "," in endereco:
        rua_sem_numero = endereco.split(",")[0].strip()
        if "Franca" not in rua_sem_numero: rua_sem_numero = f"{rua_sem_numero}, Franca, SP, Brasil"
        params = {'q': rua_sem_numero, 'format': 'json', 'limit': 1}
        try:
            res = requests.get(url, headers=headers, params=params)
            dados = res.json()
            if dados: return dados[0]['lat'], dados[0]['lon']
        except: pass
    return None, None

def gerar_pdf(ordem_entregas, nome_motorista):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    
    if os.path.exists(caminho_logo):
        c.drawImage(caminho_logo, 40, altura - 80, width=120, height=45, preserveAspectRatio=True, mask='auto')
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, altura - 50, "LoGuii Solução Logística")
    
    c.setFont("Helvetica", 10)
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
    c.drawString(180, altura - 65, f"Gerado em: {data_atual}")
    
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
        if y < 80:
            c.showPage()
            y = altura - 50
            
        prefixo = f"[URGENTE {p.get('horario', '')}] " if p.get('urgente') else ""
        if p.get('urgente'): c.setFillColorRGB(0.8, 0, 0)
            
        c.setFont("Helvetica-Bold", 12)
        num_pedido_str = f" | Pedido: {p['pedido_num']}" if p.get('pedido_num') else ""
        c.drawString(50, y, f"[{idx+1}] {prefixo}Cliente: {p['cliente']}{num_pedido_str}")
        c.setFillColorRGB(0, 0, 0) 
        y -= 15
        
        c.setFont("Helvetica", 11)
        c.drawString(50, y, f"Endereço: {p['endereco']}")
        y -= 20
        c.rect(largura - 70, y + 10, 15, 15)
        y -= 10

    c.line(50, y - 5, largura - 50, y - 5)
    y -= 25
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "📍 RETORNO: Base União Embalagens")
    y -= 15
    c.setFont("Helvetica", 11)
    c.drawString(50, y, "Endereço: Rua Doutor Ivom Rodrigues Pereira, 5078")
        
    c.save()
    buffer.seek(0)
    return buffer

if imagens_para_processar:
    for arq_imagem in imagens_para_processar:
        image = Image.open(arq_imagem)
        file_id = getattr(arq_imagem, "name", f"camera_{time.time()}")
        
        if not any(p.get("uid") == file_id for p in st.session_state.pendentes):
            dados = extrair_dados_imagem(image)
            dados["uid"] = file_id
            st.session_state.pendentes.append(dados)
            salvar_pendentes(st.session_state.pendentes)

# --- LISTAGEM DE PENDENTES (POOL DE ENTREGAS) ---
st.subheader("📋 Fila de Pedidos Pendentes")
st.markdown("Marque apenas os que irão nesta viagem. Clique no 🔕 para marcar como **URGENTE**.")

st.session_state.pendentes.sort(key=lambda x: not x.get('urgente', False))

if st.session_state.pendentes:
    c_sel, c_cli, c_end, c_ped, c_hor, c_bell, c_del = st.columns([0.5, 3, 3, 1.5, 1.5, 0.5, 0.5])
    c_cli.markdown("**Cliente**")
    c_end.markdown("**Endereço**")
    c_ped.markdown("**Nº Ped.**")
    c_hor.markdown("**Horário**")
    st.divider()

    for i, p in enumerate(st.session_state.pendentes):
        col_sel, col_cli, col_end, col_ped, col_hor, col_bell, col_del = st.columns([0.5, 3, 3, 1.5, 1.5, 0.5, 0.5])
        
        p['selecionado'] = col_sel.checkbox("", value=p.get('selecionado', True), key=f"sel_{p['uid']}")
        p['cliente'] = col_cli.text_input("Cliente:", value=p['cliente'], key=f"cli_{p['uid']}", label_visibility="collapsed")
        p['endereco'] = col_end.text_input("Endereço:", value=p['endereco'], key=f"end_{p['uid']}", label_visibility="collapsed")
        p['pedido_num'] = col_ped.text_input("Pedido:", value=p.get('pedido_num', ''), key=f"ped_{p['uid']}", label_visibility="collapsed")
        
        if p.get('urgente', False):
            p['horario'] = col_hor.text_input("Horário:", value=p.get('horario', ''), key=f"hor_{p['uid']}", placeholder="Ex: 14h00", label_visibility="collapsed")
        else:
            col_hor.write("")

        btn_sino = "🔔" if p.get('urgente', False) else "🔕"
        if col_bell.button(btn_sino, key=f"urg_{p['uid']}", help="Marcar/Desmarcar Urgência"):
            p['urgente'] = not p.get('urgente', False)
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()

        if col_del.button("🗑️", key=f"del_{p['uid']}"):
            st.session_state.pendentes.pop(i)
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()

    if st.button("🗑️ Limpar Toda a Fila de Pendentes"):
        st.session_state.pendentes = []
        salvar_pendentes(st.session_state.pendentes)
        st.rerun()
else:
    st.info("A fila está vazia. Adicione pedidos usando o menu lateral.")

salvar_pendentes(st.session_state.pendentes)

# --- OTIMIZAÇÃO E GERAÇÃO DA ROTA ---
st.subheader("🗺️ Otimização e Impressão")
nome_motorista = st.text_input("👨‍✈️ Nome do Motorista (Opcional - Sairá no PDF):", placeholder="Ex: Roberto")

pedidos_selecionados = [p for p in st.session_state.pendentes if p.get('selecionado', True)]

if st.button("🗺️ Gerar Rota Otimizada", type="primary"):
    if len(pedidos_selecionados) < 1:
        st.warning("Selecione pelo menos um endereço na fila para gerar a rota.")
    else:
        with st.spinner("Analisando distâncias e calculando rotas otimizadas com inteligência de urgência..."):
            origem_texto = "Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP, Brasil"
            enderecos_validos = []
            
            lat_o, lon_o = geocodificar(origem_texto)
            if not (lat_o and lon_o):
                st.error("Erro: Não foi possível localizar o endereço de origem padrão.")
                st.stop()
            
            for p in pedidos_selecionados:
                end_completo = f"{p['endereco']}, Franca - SP, Brasil"
                lat, lon = geocodificar(end_completo)
                if lat and lon:
                    p['lat'] = lat
                    p['lon'] = lon
                    enderecos_validos.append(p)
                else:
                    st.warning(f"⚠️ Aviso: O GPS não achou o endereço exato nem a rua próxima de: {p['endereco']}")
                time.sleep(1) 

            if len(enderecos_validos) > 0:
                # Usa a Inteligência em Python no lugar do servidor externo (100x mais rápido e nunca cai)
                ordem_entregas = otimizar_rota_com_urgencia(lat_o, lon_o, enderecos_validos)
                
                st.success("Rota gerada com sucesso! A inteligência do sistema priorizou as entregas urgentes mantendo a melhor eficiência.")
                
                st.subheader("📍 Ordem Sugerida de Entregas")
                for idx, p in enumerate(ordem_entregas):
                    urg_text = f" **[URG. {p.get('horario', '')}]** " if p.get('urgente') else ""
                    num_pedido_tela = f" (Ped: {p['pedido_num']})" if p.get('pedido_num') else ""
                    st.markdown(f"**Parada {idx+1}:** {urg_text}{p['cliente']}{num_pedido_tela} — *{p['endereco']}*")
                
                st.markdown(f"**📍 Retorno:** Base União Embalagens — *Rua Doutor Ivom Rodrigues Pereira, 5078*")
                
                origem_link = "Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP".replace(" ", "+")
                destino_final = origem_link 
                pontos_intermediarios = "|".join([f"{p['endereco']}, Franca, SP".replace(" ", "+") for p in ordem_entregas])
                link_maps = f"https://www.google.com/maps/dir/?api=1&origin={origem_link}&destination={destino_final}&waypoints={pontos_intermediarios}"
                    
                st.markdown(f"[🔗 Abrir Rota no Aplicativo do Google Maps]({link_maps})", unsafe_allow_html=True)
                
                st.divider()
                pdf_arquivo = gerar_pdf(ordem_entregas, nome_motorista)
                st.download_button(
                    label="📄 Baixar PDF com Checklist da Rota",
                    data=pdf_arquivo,
                    file_name=f"LoGuii_Rota_{datetime.now().strftime('%d%m%Y_%H%M')}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
                
                # Remove os itens roteirizados da fila permanentemente
                st.session_state.pendentes = [p for p in st.session_state.pendentes if not p.get('selecionado', False)]
                salvar_pendentes(st.session_state.pendentes)
                
                nova_rota = {
                    "timestamp": time.time(),
                    "data_formatada": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "motorista": nome_motorista if nome_motorista else "Não informado",
                    "entregas": ordem_entregas,
                    "link_maps": link_maps
                }
                gerenciar_historico(acao='adicionar', dados=nova_rota)
            else:
                st.error("Não foram encontrados endereços válidos suficientes para criar uma rota.")

# --- HISTÓRICO DE ROTAS ---
st.divider()
st.subheader("🕒 Histórico de Rotas (Últimas 48h)")
historico = gerenciar_historico()

if historico:
    for i, rota in enumerate(historico):
        with st.expander(f"🛣️ Rota de {rota['data_formatada']} - Motorista: {rota['motorista']} ({len(rota['entregas'])} entregas)"):
            st.markdown(f"[🔗 Abrir Rota no Google Maps]({rota['link_maps']})", unsafe_allow_html=True)
            for p in rota['entregas']:
                urg = f" **[URG. {p.get('horario', '')}]**" if p.get('urgente') else ""
                num = f" (Ped: {p['pedido_num']})" if p.get('pedido_num') else ""
                st.write(f"-{urg} {p['cliente']}{num}: *{p['endereco']}*")
            
            col_b1, col_b2, col_b3 = st.columns([2, 2, 2])
            with col_b1:
                pdf_hist = gerar_pdf(rota['entregas'], rota['motorista'])
                st.download_button(label="📄 Re-imprimir PDF", data=pdf_hist, file_name=f"LoGuii_Hist_{i}.pdf", mime="application/pdf", key=f"dl_hist_{i}")
            
            with col_b2:
                if st.button("✏️ Editar (Devolver p/ Fila)", key=f"edit_hist_{i}", help="Apagará do histórico e devolverá para a fila de pendentes."):
                    for p_hist in rota['entregas']:
                        p_hist['uid'] = f"hist_{time.time()}_{p_hist['cliente']}"
                        p_hist['selecionado'] = True
                        st.session_state.pendentes.append(p_hist)
                    salvar_pendentes(st.session_state.pendentes)
                    gerenciar_historico(acao='excluir', idx=i)
                    st.rerun()
            
            with col_b3:
                if st.button("🗑️ Excluir Rota", key=f"del_hist_{i}", type="secondary"):
                    gerenciar_historico(acao='excluir', idx=i)
                    st.rerun()
else:
    st.info("Nenhuma rota recente salva no histórico ainda.")
