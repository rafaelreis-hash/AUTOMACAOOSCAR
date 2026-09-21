import base64
import hashlib
import hmac
import json
import os
import random
import time
import unicodedata
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
# --- NXT Portal ---
URL_BASE_NXT = "https://console.nxt4insight.com"
LOGIN_URL_NXT = f"{URL_BASE_NXT}/Account/Login"
TIMELINE_URL = f"{URL_BASE_NXT}/Movimentacao/LoadTimeLine"
CREATE_VIEW_URL = f"{URL_BASE_NXT}/Movimentacao/Create"
CREATE_INVENTARIO_URL = f"{URL_BASE_NXT}/Movimentacao/CreateInventario"

USUARIO_NXT = "rafael.reis@mgitech.com.br"
SENHA_NXT = "R@fa140033"

# ID fixo do organograma de destino no NXT
ID_ORGANOGRAMA_DESTINO = 31096251

# --- Cloud4Mobile (C4M) ---
BASE_URL_C4M = "https://api.cloud4mobile.com.br"
CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")

NOME_GRUPO_ALVO_C4M = "Startup"
PACKAGE_ALVO_C4M = "com.safira.app"

# --- Lista Única de IMEIs ---
LISTA_IMEIS = LISTA_IMEIS = [
    "351989270713463",
    "351989270869877",
    "352189677036316",
    "353297230712973",
    "353297230801057",
    "353297230801180",
    "353297230801354",
    "353297230868783",
    "353297230870235",
    "353297230897360",
    "353297230898897",
    "353297231780102",
    "353297234770589",
    "354291421596872",
    "354291424489414",
    "354378786636482",
    "354378787115155",
    "354492131037013"
]

# ==============================================================================
# MÓDULO 1: FUNÇÕES DO PORTAL NXT
# ==============================================================================
def autenticar_nxt4insight(session: requests.Session) -> bool:
    try:
        res = session.get(LOGIN_URL_NXT, timeout=15)
        if res.status_code != 200:
            return False

        soup = BeautifulSoup(res.text, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_input or not token_input.get("value"):
            return False

        payload = {
            "loginViewModel.Login": USUARIO_NXT,
            "loginViewModel.Password": SENHA_NXT,
            "__RequestVerificationToken": token_input.get("value"),
        }

        headers = {
            "Referer": LOGIN_URL_NXT,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        login_res = session.post(
            LOGIN_URL_NXT, data=payload, headers=headers, timeout=15
        )
        return (
            login_res.status_code == 200
            and "Account/Login" not in login_res.url
        )
    except Exception as e:
        print(f"❌ [NXT] Erro ao autenticar: {e}")
        return False


def buscar_ultima_locacao_timeline(session: requests.Session, dispositivo_id: str) -> dict:
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{URL_BASE_NXT}/Movimentacao",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    params = {"Id": dispositivo_id}

    try:
        res = session.get(TIMELINE_URL, params=params, headers=headers, timeout=15)
        if res.status_code == 200:
            dados = res.json()
            eventos = []
            if isinstance(dados, list):
                eventos = dados
            elif isinstance(dados, dict):
                eventos = dados.get("data") or dados.get("Items") or dados.get("list") or []

            if eventos:
                campo_data = None
                for chave in ["DataHora", "Data", "Date", "CreatedAt", "DataCriacao"]:
                    if chave in eventos[0]:
                        campo_data = chave
                        break

                if campo_data:
                    eventos_ordenados = sorted(eventos, key=lambda x: str(x.get(campo_data, "")))
                    return eventos_ordenados[-1]

                return eventos[-1]
    except Exception as e:
        print(f"❌ [NXT] Erro ao buscar timeline ({dispositivo_id}): {e}")

    return {}


def obter_token_verificacao_form(session: requests.Session) -> str:
    try:
        res = session.get(CREATE_VIEW_URL, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            token_input = soup.find("input", {"name": "__RequestVerificationToken"})
            if token_input:
                return token_input.get("value", "")
    except Exception as e:
        print(f"⚠️ [NXT] Erro ao obter token anti-forgery: {e}")
    return ""


def movimentar_dispositivo_inventario(
    session: requests.Session,
    lista_ativos: str,
    id_organograma: int,
    id_empresa: int,
    numero_chamado: str = "AUTOMACAO-LOTE",
    observacoes: str = "Movimentação em lote via automação Python",
) -> dict:
    request_token = obter_token_verificacao_form(session)
    data_inicio_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000") + "Z"

    form_page_dict = {
        "ListaAtivos": str(lista_ativos),
        "IdOrganograma": str(id_organograma),
        "IdColaborador": 0,
        "IdEmpresa": str(id_empresa),
        "DataInicio": data_inicio_iso,
        "Observacoes": observacoes,
        "NumeroChamado": numero_chamado,
        "IdTipoFinalizacao": 0,
        "IsFimCiclo": None,
        "NumNfRemessa": "",
    }

    form_page_json = json.dumps(form_page_dict, separators=(",", ":"))
    multipart_fields = {"formPage": (None, form_page_json)}

    if request_token:
        multipart_fields["__RequestVerificationToken"] = (None, request_token)

    headers = {
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": CREATE_VIEW_URL,
        "Origin": URL_BASE_NXT,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        res = session.post(
            CREATE_INVENTARIO_URL,
            params={"formPage": form_page_json},
            files=multipart_fields,
            headers=headers,
            timeout=30,
        )
        if res.status_code == 200:
            try:
                return res.json()
            except json.JSONDecodeError:
                return {"status": "sucesso", "resposta_raw": res.text}
    except Exception as e:
        print(f"❌ [NXT] Erro ao enviar requisição de movimentação: {e}")

    return {}


# ==============================================================================
# MÓDULO 2: FUNÇÕES DO CLOUD4MOBILE (C4M)
# ==============================================================================
def generate_token_c4m(url: str, consumer_key: str, consumer_secret: str, method: str = "GET") -> str:
    timestamp = int(time.time())
    nonce = str(random.randint(100000, 999999))

    auth = {
        "consumer_key": consumer_key,
        "nonce": nonce,
        "timestamp": timestamp,
        "version": "1.0",
        "signature": "",
    }

    input_str = (
        consumer_secret
        + consumer_key
        + nonce
        + str(timestamp)
        + "1.0"
        + method.upper()
        + url.upper()
    )

    signature = hmac.new(
        consumer_secret.encode(), input_str.encode(), hashlib.sha256
    ).digest()

    auth["signature"] = base64.b64encode(signature).decode()
    return base64.b64encode(json.dumps(auth).encode()).decode()


def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()


def obter_id_por_imei_c4m(identificador: str) -> str:
    url = f"{BASE_URL_C4M}/devices/search?%24top=20&%24skip=0&%24inlinecount=allpages"
    token = generate_token_c4m(url, CONSUMER_KEY, CONSUMER_SECRET, "POST")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "statusFilter": 1,
        "groupId": None,
        "platformType": None,
        "searchTermField": 0,
        "searchTerms": [str(identificador).strip()],
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            dados = res.json()
            itens = dados if isinstance(dados, list) else (dados.get("items") or dados.get("value") or [])
            if itens:
                return itens[0].get("id") or itens[0].get("Id")
    except Exception as e:
        print(f"❌ [C4M] Erro ao consultar {identificador}: {e}")

    return None


def obter_id_grupo_por_nome_c4m(nome_grupo: str) -> int:
    endpoints = ["/statistics/groups", "/groups"]
    alvo_norm = normalizar_texto(nome_grupo)

    for ep in endpoints:
        url = f"{BASE_URL_C4M}{ep}"
        token = generate_token_c4m(url, CONSUMER_KEY, CONSUMER_SECRET, "GET")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                dados = res.json()
                grupos = dados if isinstance(dados, list) else (dados.get("items") or dados.get("value") or dados.get("groups") or [])
                for g in grupos:
                    nome_bruto = str(g.get("name") or g.get("Name") or g.get("groupName") or g.get("GroupName") or "").strip()
                    if normalizar_texto(nome_bruto) == alvo_norm:
                        return g.get("id") or g.get("Id") or g.get("groupId") or g.get("GroupId")
        except Exception as e:
            print(f"⚠️ [C4M] Erro ao consultar endpoint {ep}: {e}")

    return None


def alterar_grupo_dispositivo_c4m(device_id: int, group_id: int) -> bool:
    url = f"{BASE_URL_C4M}/groups/{group_id}/devices"
    token = generate_token_c4m(url, CONSUMER_KEY, CONSUMER_SECRET, "POST")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"id": device_id}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        return res.status_code in [200, 201, 202, 204]
    except Exception:
        return False


def enviar_limpeza_app_c4m(device_id: int, package_name: str) -> bool:
    url = f"{BASE_URL_C4M}/devices/{device_id}/operations"
    token = generate_token_c4m(url, CONSUMER_KEY, CONSUMER_SECRET, "POST")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"operationType": 37, "packageName": package_name}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        return res.status_code in [200, 201, 202]
    except Exception:
        return False


# ==============================================================================
# FLUXO PRINCIPAL UNIFICADO
# ==============================================================================
def executar_fluxo_unificado():
    print("=" * 80)
    print("🚀 INICIANDO AUTOMAÇÃO UNIFICADA: PORTAL NXT + CLOUD4MOBILE")
    print("=" * 80)

    # 1. Validação de Credenciais C4M
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        print("❌ Erro: CONSUMER_KEY e/ou CONSUMER_SECRET não configurados no ambiente.")
        return

    # 2. Busca ID do Grupo de Destino no C4M
    print(f"🔍 Localizando Grupo C4M '{NOME_GRUPO_ALVO_C4M}'...")
    group_id_c4m = obter_id_grupo_por_nome_c4m(NOME_GRUPO_ALVO_C4M)
    if not group_id_c4m:
        print(f"❌ Erro: Grupo '{NOME_GRUPO_ALVO_C4M}' não encontrado no C4M. Interrompendo.")
        return
    print(f"✅ Grupo C4M encontrado! ID: {group_id_c4m}\n")

    # 3. Autenticação no Portal NXT
    nxt_session = requests.Session()
    print("🔐 Autenticando no Portal NXT...")
    if not autenticar_nxt4insight(nxt_session):
        print("❌ Falha na autenticação do Portal NXT. Interrompendo.")
        return
    print("✅ Autenticado no Portal NXT com sucesso!\n")

    resumo = {
        "nxt_sucesso": [],
        "nxt_ignorado_estoque": [],
        "nxt_sem_timeline": [],
        "nxt_falha_api": [],
        "c4m_sucesso": [],
        "c4m_nao_encontrado": [],
        "c4m_falha_grupo": [],
        "c4m_falha_limpeza": [],
    }

    # 4. Iteração nos IMEIs
    total = len(LISTA_IMEIS)
    for idx, imei in enumerate(LISTA_IMEIS, start=1):
        print("-" * 80)
        print(f"📱 [{idx}/{total}] Processando IMEI: {imei}")

        # ----------------------------------------------------------------------
        # PASSO A: MOVIMENTAÇÃO NO PORTAL NXT
        # ----------------------------------------------------------------------
        print("  🔹 [NXT] Consultando timeline...")
        ultima_locacao = buscar_ultima_locacao_timeline(nxt_session, imei)

        if not ultima_locacao:
            print("  ⚠️ [NXT] Dispositivo sem registros na timeline.")
            resumo["nxt_sem_timeline"].append(imei)
        else:
            nome_vinculado = str(ultima_locacao.get("nomevinculado") or "").strip().upper()
            organograma_colab = str(ultima_locacao.get("organogramacolaboador") or "").strip().upper()
            id_empresa = ultima_locacao.get("idempresa", 6576)

            if nome_vinculado.startswith("ESTOQUE") or organograma_colab.startswith("ESTOQUE"):
                print("  ⛔ [NXT] Dispositivo já em estoque. Movimentação NXT ignorada.")
                resumo["nxt_ignorado_estoque"].append(imei)
            else:
                res_nxt = movimentar_dispositivo_inventario(
                    nxt_session,
                    lista_ativos=imei,
                    id_organograma=ID_ORGANOGRAMA_DESTINO,
                    id_empresa=id_empresa,
                )
                ok_status = str(res_nxt.get("Ok", "")).lower()
                if ok_status == "true" or res_nxt.get("status") == "sucesso":
                    print(f"  ✅ [NXT] Movimentado para o organograma {ID_ORGANOGRAMA_DESTINO}!")
                    resumo["nxt_sucesso"].append(imei)
                else:
                    print(f"  ❌ [NXT] Falha na movimentação: {res_nxt.get('Msg', 'Erro desconhecido')}")
                    resumo["nxt_falha_api"].append(imei)

        # ----------------------------------------------------------------------
        # PASSO B: GERENCIAMENTO E LIMPEZA NO CLOUD4MOBILE
        # ----------------------------------------------------------------------
        print("  🔹 [C4M] Localizando dispositivo na plataforma...")
        device_id_c4m = obter_id_por_imei_c4m(imei)

        if not device_id_c4m:
            print("  ❌ [C4M] IMEI não encontrado no Cloud4Mobile.")
            resumo["c4m_nao_encontrado"].append(imei)
        else:
            # Troca de grupo
            ok_grupo = alterar_grupo_dispositivo_c4m(device_id_c4m, group_id_c4m)
            if ok_grupo:
                print(f"  ✅ [C4M] Movido para o grupo ID {group_id_c4m}.")
            else:
                print("  ❌ [C4M] Falha ao alterar o grupo.")
                resumo["c4m_falha_grupo"].append(imei)

            # Envio de ordem de limpeza do app
            ok_limpeza = enviar_limpeza_app_c4m(device_id_c4m, PACKAGE_ALVO_C4M)
            if ok_limpeza:
                print(f"  ✅ [C4M] Ordem de limpeza enviada para '{PACKAGE_ALVO_C4M}'.")
                if ok_grupo:
                    resumo["c4m_sucesso"].append(imei)
            else:
                print("  ❌ [C4M] Falha ao enviar ordem de limpeza.")
                resumo["c4m_falha_limpeza"].append(imei)

        time.sleep(0.5)

    # ==========================================================================
    # RELATÓRIO FINAL
    # ==========================================================================
    print("\n" + "=" * 80)
    print("📊 RELATÓRIO FINAL DE EXECUÇÃO UNIFICADA")
    print("=" * 80)
    print("--- PORTAL NXT ---")
    print(f"  ✅ Movimentados com sucesso ({len(resumo['nxt_sucesso'])}): {resumo['nxt_sucesso']}")
    print(f"  ⛔ Já estavam em estoque ({len(resumo['nxt_ignorado_estoque'])}): {resumo['nxt_ignorado_estoque']}")
    print(f"  ⚠️ Sem timeline ({len(resumo['nxt_sem_timeline'])}): {resumo['nxt_sem_timeline']}")
    print(f"  ❌ Rejeitados pela API NXT ({len(resumo['nxt_falha_api'])}): {resumo['nxt_falha_api']}")
    print("\n--- CLOUD4MOBILE (C4M) ---")
    print(f"  ✅ Grupo alterado e limpeza enviada ({len(resumo['c4m_sucesso'])}): {resumo['c4m_sucesso']}")
    print(f"  ❌ Dispositivo não encontrado ({len(resumo['c4m_nao_encontrado'])}): {resumo['c4m_nao_encontrado']}")
    print(f"  ❌ Falha ao mover grupo ({len(resumo['c4m_falha_grupo'])}): {resumo['c4m_falha_grupo']}")
    print(f"  ❌ Falha na ordem de limpeza ({len(resumo['c4m_falha_limpeza'])}): {resumo['c4m_falha_limpeza']}")
    print("=" * 80)


if __name__ == "__main__":
    executar_fluxo_unificado()
