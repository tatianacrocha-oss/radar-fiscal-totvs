#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Radar Fiscal TOTVS - coleta, classifica e publica noticias fiscais/tributarias."""

import argparse
import hashlib
import html
import json
import logging
import os
import re
import smtplib
import ssl
import sys
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_JS_PATH = BASE_DIR / "noticias_data.js"
HISTORICO_PATH = BASE_DIR / "noticias_historico.json"
LOG_PATH = BASE_DIR / "radar_fiscal.log"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
HTTP_TIMEOUT = 15

EXTENSOES_IMAGEM = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
SEGMENTOS_NAVEGACAO_IGNORADOS = {
    "carrossel", "colecao", "coleção", "todas-as-noticias", "ultimas-noticias",
    "mais-noticias", "destaques", "banners", "view", "sped",
}
TRECHOS_NAVEGACAO_IGNORADOS = ("servico_detalhado", "carta-de-servicos", "cartadeservicos")

PREFIXO_DATA_LONGA = re.compile(
    r"^\d{1,2}\s+de\s+[A-Za-zçÇãÃéÉ]+\s+de\s+\d{4}(\s*[àa]s\s*\d{1,2}[:h]\d{2})?\s+", re.IGNORECASE
)
PREFIXO_ETIQUETA_MAIUSCULA = re.compile(r"^[A-ZÀ-Ü][A-ZÀ-Ü\s\-/]{2,49}\s+(?=[A-ZÀ-Ü][a-zà-ü])")


def limpar_prefixos_ruido(titulo: str) -> str:
    """Remove selos tipo 'LEGISLAÇÃO EM VIGOR' ou datas extensas coladas na frente do titulo real.

    Comuns em portais estaduais (Liferay, Contabeis) que colocam a categoria/data
    dentro do mesmo elemento HTML do titulo da noticia.
    """
    titulo = PREFIXO_DATA_LONGA.sub("", titulo)
    titulo = PREFIXO_ETIQUETA_MAIUSCULA.sub("", titulo)
    return titulo.strip()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("radar_fiscal")


def parece_link_de_navegacao(link: str) -> bool:
    """Filtra itens de menu/imagem que o RSS de alguns portais gov.br mistura com noticias reais."""
    link_lower = link.lower()
    if any(f"{ext}/" in link_lower or link_lower.endswith(ext) for ext in EXTENSOES_IMAGEM):
        return True
    if any(trecho in link_lower for trecho in TRECHOS_NAVEGACAO_IGNORADOS):
        return True
    segmentos = [s for s in urlparse(link_lower).path.split("/") if s]
    if not segmentos:
        return True
    ultimo_segmento = segmentos[-1]
    if re.fullmatch(r"\d{4}", ultimo_segmento) and 2015 <= int(ultimo_segmento) <= 2035:
        return True  # pasta tipo /noticias/2026 (ano) - nao confundir com IDs numericos de aviso/materia
    return ultimo_segmento in SEGMENTOS_NAVEGACAO_IGNORADOS


def carregar_json(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def gerar_id_noticia(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]


def limpar_texto(texto: str) -> str:
    return " ".join(html.unescape(texto or "").split()).strip()


RODAPE_WORDPRESS = re.compile(r"O post .*? apareceu primeiro em .*?\.?\s*$", re.IGNORECASE | re.DOTALL)


def limpar_resumo_html(resumo_html: str) -> str:
    """Remove tags HTML e o rodape padrao 'O post X apareceu primeiro em Y' que
    plugins como o Jetpack anexam ao resumo de feeds RSS em WordPress."""
    texto = BeautifulSoup(resumo_html or "", "html.parser").get_text(" ")
    texto = RODAPE_WORDPRESS.sub("", texto)
    return limpar_texto(texto)


def requisitar(url: str) -> requests.Response:
    """GET com fallback sem verificacao de certificado.

    Varios sites de SEFAZ estadual tem cadeia de certificado ICP-Brasil incompleta
    no servidor. Como aqui so fazemos leitura de noticias publicas (nunca enviamos
    dados), tentamos primeiro com verificacao normal e so relaxamos em caso de
    SSLError, deixando um aviso claro no log.
    """
    try:
        resposta = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
    except requests.exceptions.SSLError:
        log.warning("Certificado invalido em %s - repetindo sem verificacao de SSL.", url)
        resposta = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, verify=False)
    resposta.raise_for_status()
    return resposta


def buscar_rss(fonte: dict) -> list[dict]:
    resposta = requisitar(fonte["url"])
    feed = feedparser.parse(resposta.content)
    itens = []
    for entrada in feed.entries:
        titulo = limpar_texto(getattr(entrada, "title", ""))
        link = getattr(entrada, "link", "")
        if not titulo or not link:
            continue
        resumo = limpar_resumo_html(getattr(entrada, "summary", ""))
        data_pub = getattr(entrada, "published", "") or getattr(entrada, "updated", "")
        itens.append({"titulo": titulo, "link": link, "resumo": resumo, "data_publicacao": data_pub})
    return itens


def buscar_gov_br_html(fonte: dict) -> list[dict]:
    """Layout padrao do 'Portal gov.br' (Plone): ul.noticias > li > h2.titulo a / span.data."""
    resposta = requisitar(fonte["url"])
    sopa = BeautifulSoup(resposta.text, "html.parser")
    itens = []
    for item in sopa.select("ul.noticias li"):
        titulo_tag = item.select_one("h2.titulo a, .titulo a")
        if not titulo_tag:
            continue
        titulo = limpar_texto(titulo_tag.get_text())
        link = urljoin(fonte["url"], titulo_tag.get("href", ""))
        data_tag = item.select_one(".data")
        data_publicacao = limpar_texto(data_tag.get_text()) if data_tag else ""
        descricao_tag = item.select_one(".descricao")
        resumo = limpar_texto(descricao_tag.get_text()) if descricao_tag else ""
        if data_publicacao and resumo.startswith(data_publicacao):
            resumo = limpar_texto(resumo[len(data_publicacao):].lstrip("- "))
        if not titulo or not link:
            continue
        itens.append({"titulo": titulo, "link": link, "resumo": resumo, "data_publicacao": data_publicacao})
    return itens


def buscar_svrs_avisos_html(fonte: dict) -> list[dict]:
    """Portal Conformidade Facil (ENCAT/SVRS): ul.media-list > li > h3.media-heading a / time[datetime]."""
    resposta = requisitar(fonte["url"])
    sopa = BeautifulSoup(resposta.text, "html.parser")
    itens = []
    for item in sopa.select("ul.media-list li.media"):
        titulo_tag = item.select_one("h3.media-heading a, .media-heading a")
        href = titulo_tag.get("href") if titulo_tag else None
        if not href or href.strip() in ("#", "") or href.startswith("javascript:"):
            continue
        titulo = limpar_texto(titulo_tag.get_text())
        link = urljoin(fonte["url"], href)
        data_tag = item.select_one("time[datetime]")
        data_publicacao = limpar_texto(data_tag.get_text()) if data_tag else ""
        autor_tag = item.select_one(".lista-categoria a")
        resumo = ("Publicado por " + limpar_texto(autor_tag.get_text())) if autor_tag else ""
        if not titulo:
            continue
        itens.append({"titulo": titulo, "link": link, "resumo": resumo, "data_publicacao": data_publicacao})
    return itens


CLASSES_CANDIDATAS = ("noticia", "news", "post", "materia", "titulo", "title", "artigo")
CLASSES_ANCESTRAL_IGNORADAS = re.compile(
    r"menu|nav|breadcrumb|sidebar|footer|header|sitemap|rodape|cabecalho|mapa-do-site", re.IGNORECASE
)


def esta_em_area_de_navegacao(tag) -> bool:
    """Descarta links de menu/rodape/sitemap que tambem carregam classes como 'titulo' ou 'item'."""
    for ancestral in tag.parents:
        classes = ancestral.get("class") if hasattr(ancestral, "get") else None
        if classes and CLASSES_ANCESTRAL_IGNORADAS.search(" ".join(classes)):
            return True
    return False


def buscar_generic_html(fonte: dict) -> list[dict]:
    """Heuristica generica para sites sem RSS/layout conhecido (ex.: a maioria das SEFAZ estaduais).

    Cada site de estado usa uma plataforma diferente (Drupal, SharePoint, CMS proprio),
    entao aqui procuramos qualquer link cujo container (li/div/article) tenha uma classe
    com nome sugestivo de noticia e um texto longo o suficiente para ser um titulo real.
    Pode retornar 0 itens em sites muito dinamicos (JS) - nesse caso ajuste o seletor
    manualmente em config/sources.json ou reporte para revisao.
    """
    resposta = requisitar(fonte["url"])
    sopa = BeautifulSoup(resposta.text, "html.parser")

    candidatos = []
    for classe in CLASSES_CANDIDATAS:
        candidatos.extend(sopa.select(f'[class*="{classe}"]'))

    vistos = set()
    itens = []
    for container in candidatos:
        classes_container = " ".join(container.get("class") or [])
        if re.search(r"\bno[-_]?title\b|\bsem[-_]?titulo\b", classes_container, re.IGNORECASE):
            continue  # ex.: classe "no-title" (Liferay/Bootstrap) nao e um titulo de noticia
        if container.name == "a":
            link_tag = container
        else:
            link_tag = container.select_one("a[href]") or container.find_parent("a", href=True)
        if not link_tag or not link_tag.get("href"):
            continue
        if esta_em_area_de_navegacao(container):
            continue
        titulo = limpar_texto(container.get_text())
        titulo = re.sub(r"^\d{1,2}h\d{2}\s+", "", titulo)
        titulo = limpar_prefixos_ruido(titulo)
        if len(titulo) < 25 or len(titulo) > 200:
            continue  # titulo real de noticia nao e um paragrafo/menu inteiro
        if "exibindo 0 a 0 de 0" in titulo.lower():
            continue  # mensagem de lista vazia do site, nao e noticia
        link = urljoin(fonte["url"], link_tag["href"])
        if link in vistos:
            continue
        vistos.add(link)

        bloco = container.find_parent(["p", "li", "article"])
        resumo = ""
        if bloco:
            texto_bloco = limpar_prefixos_ruido(re.sub(r"^\d{1,2}h\d{2}\s+", "", limpar_texto(bloco.get_text())))
            if texto_bloco.startswith(titulo):
                resumo = texto_bloco[len(titulo):].strip(" -–:")

        itens.append({"titulo": titulo, "link": link, "resumo": resumo, "data_publicacao": ""})
    return itens


BUSCADORES = {
    "rss": buscar_rss,
    "gov_br_html": buscar_gov_br_html,
    "generic_html": buscar_generic_html,
    "svrs_avisos_html": buscar_svrs_avisos_html,
}


def classificar_impacto(texto_lower: str, classificacao: dict) -> str:
    if any(termo in texto_lower for termo in classificacao["impacto_alto"]):
        return "alto"
    if any(termo in texto_lower for termo in classificacao["impacto_baixo"]):
        return "baixo"
    return "médio"


def classificar_tags(texto_lower: str, classificacao: dict) -> list[str]:
    tags = []
    for tag, palavras_chave in classificacao["tags"].items():
        if any(termo in texto_lower for termo in palavras_chave):
            tags.append(tag)
    return tags


def processar_fonte(fonte: dict, classificacao: dict) -> list[dict]:
    buscador = BUSCADORES.get(fonte["tipo"])
    if not buscador:
        log.warning("Fonte '%s' com tipo desconhecido: %s", fonte["id"], fonte["tipo"])
        return []

    try:
        itens_brutos = buscador(fonte)
    except Exception as erro:
        log.warning("Falha ao coletar '%s' (%s): %s", fonte["nome"], fonte["url"], erro)
        return []

    exclusoes = fonte.get("excluir_se_link_contem", [])
    itens_filtrados = [
        item
        for item in itens_brutos
        if item["link"]
        and not parece_link_de_navegacao(item["link"])
        and not any(trecho in item["link"] for trecho in exclusoes)
    ][: fonte["max_itens"]]

    if not itens_filtrados:
        log.info("Fonte '%s' nao retornou noticias nesta coleta.", fonte["nome"])

    noticias = []
    for item in itens_filtrados:
        texto_lower = f"{item['titulo']} {item['resumo']}".lower()
        noticias.append(
            {
                "id": gerar_id_noticia(item["link"]),
                "titulo": item["titulo"],
                "resumo": item["resumo"] or item["titulo"],
                "link": item["link"],
                "fonte": fonte["nome"],
                "esfera": fonte["esfera"],
                "uf": fonte.get("uf", ""),
                "data_publicacao": item["data_publicacao"],
                "impacto": classificar_impacto(texto_lower, classificacao),
                "tags": classificar_tags(texto_lower, classificacao),
                "coletado_em": datetime.now().isoformat(timespec="seconds"),
            }
        )
    log.info("Fonte '%s': %d noticia(s) coletada(s).", fonte["nome"], len(noticias))
    return noticias


def coletar_tudo(sources: dict, classificacao: dict) -> list[dict]:
    todas_noticias = []
    for fonte in sources["fontes"]:
        todas_noticias.extend(processar_fonte(fonte, classificacao))
        time.sleep(0.5)
    return todas_noticias


def carregar_historico() -> dict:
    if HISTORICO_PATH.exists():
        return carregar_json(HISTORICO_PATH)
    return {"noticias": {}}


def salvar_historico_atualizado(historico: dict, noticias_novas: list[dict], dias_retencao: int) -> list[dict]:
    for noticia in noticias_novas:
        existente = historico["noticias"].get(noticia["id"])
        noticia["primeira_vez_em"] = existente.get("primeira_vez_em", existente.get("coletado_em")) if existente else noticia["coletado_em"]
        historico["noticias"][noticia["id"]] = noticia

    limite = datetime.now() - timedelta(days=dias_retencao)
    historico["noticias"] = {
        id_noticia: noticia
        for id_noticia, noticia in historico["noticias"].items()
        if datetime.fromisoformat(noticia["coletado_em"]) >= limite
    }

    with open(HISTORICO_PATH, "w", encoding="utf-8") as arquivo:
        json.dump(historico, arquivo, ensure_ascii=False, indent=2)

    return sorted(historico["noticias"].values(), key=lambda n: n["coletado_em"], reverse=True)


def montar_boletim_texto(noticias_do_dia: list[dict], config: dict) -> str:
    if not noticias_do_dia:
        return "Nenhuma noticia nova coletada hoje."

    linhas = [f"Boletim Radar Fiscal TOTVS - {datetime.now().strftime('%d/%m/%Y')}", ""]
    for impacto in ("alto", "médio", "baixo"):
        do_impacto = [n for n in noticias_do_dia if n["impacto"] == impacto]
        if not do_impacto:
            continue
        linhas.append(f"--- Impacto {impacto.upper()} ({len(do_impacto)}) ---")
        for noticia in do_impacto:
            linhas.append(f"* [{noticia['fonte']}] {noticia['titulo']}")
            linhas.append(f"  {noticia['link']}")
        linhas.append("")
    return "\n".join(linhas)


def enviar_email(boletim_texto: str, config: dict) -> None:
    cfg_email = config["boletim_email"]
    if not cfg_email.get("ativo"):
        log.info("Envio de e-mail desativado em config/config.json (boletim_email.ativo=false).")
        return

    senha = os.environ.get("RADAR_FISCAL_EMAIL_SENHA")
    if not senha:
        log.warning("Variavel de ambiente RADAR_FISCAL_EMAIL_SENHA nao definida. E-mail nao enviado.")
        return

    mensagem = MIMEMultipart()
    mensagem["From"] = cfg_email["email_remetente"]
    mensagem["To"] = cfg_email["email_destinatario"]
    mensagem["Subject"] = f"Boletim Radar Fiscal TOTVS - {datetime.now().strftime('%d/%m/%Y')}"
    mensagem.attach(MIMEText(boletim_texto, "plain", "utf-8"))

    contexto = ssl.create_default_context()
    with smtplib.SMTP(cfg_email["servidor_smtp"], cfg_email["porta_smtp"]) as servidor:
        servidor.starttls(context=contexto)
        servidor.login(cfg_email["email_remetente"], senha)
        servidor.send_message(mensagem)

    log.info("Boletim enviado por e-mail para %s.", cfg_email["email_destinatario"])


def gerar_noticias_data_js(noticias: list[dict], reforma_status: dict) -> None:
    dados = {
        "geradoEm": datetime.now().isoformat(timespec="seconds"),
        "noticias": noticias,
        "reforma": reforma_status,
    }
    conteudo = "const RADAR_DADOS = " + json.dumps(dados, ensure_ascii=False, indent=2) + ";\n"
    with open(DATA_JS_PATH, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)
    log.info("Arquivo %s atualizado com %d noticia(s).", DATA_JS_PATH.name, len(noticias))


def avisar_marcos_reforma(noticias_novas: list[dict]) -> None:
    relevantes = [n for n in noticias_novas if "Reforma Tributária" in n["tags"] or "IBS" in n["tags"] or "CBS" in n["tags"] or "Imposto Seletivo" in n["tags"]]
    if relevantes:
        log.info(
            "%d noticia(s) sobre Reforma Tributaria/IBS/CBS/Imposto Seletivo encontradas. "
            "Revise config/reforma_status.json se houver novo marco confirmado.",
            len(relevantes),
        )


def executar_coleta(enviar_email_forcado: bool = False) -> None:
    sources = carregar_json(CONFIG_DIR / "sources.json")
    config = carregar_json(CONFIG_DIR / "config.json")
    classificacao = carregar_json(CONFIG_DIR / "classificacao.json")
    reforma_status = carregar_json(CONFIG_DIR / "reforma_status.json")

    noticias_novas = coletar_tudo(sources, classificacao)
    historico = carregar_historico()
    noticias_atualizadas = salvar_historico_atualizado(
        historico, noticias_novas, config["historico"]["dias_retencao"]
    )

    gerar_noticias_data_js(noticias_atualizadas, reforma_status)
    avisar_marcos_reforma(noticias_novas)

    hoje = datetime.now().strftime("%Y-%m-%d")
    noticias_do_dia = [n for n in noticias_atualizadas if n["coletado_em"].startswith(hoje)]
    boletim_texto = montar_boletim_texto(noticias_do_dia, config)

    if enviar_email_forcado or datetime.now().strftime("%H:%M") == config["boletim_email"]["horario_envio"]:
        enviar_email(boletim_texto, config)


def testar_fonte(id_fonte: str) -> None:
    sources = carregar_json(CONFIG_DIR / "sources.json")
    classificacao = carregar_json(CONFIG_DIR / "classificacao.json")
    fonte = next((f for f in sources["fontes"] if f["id"] == id_fonte), None)
    if not fonte:
        print(f"Fonte '{id_fonte}' nao encontrada em config/sources.json.")
        return

    noticias = processar_fonte(fonte, classificacao)
    print(f"\n{len(noticias)} noticia(s) encontrada(s) em '{fonte['nome']}' ({fonte['url']}):\n")
    for noticia in noticias:
        print(f"- [{noticia['impacto']}] {noticia['titulo']}")
        print(f"  {noticia['link']}")


def executar_modo_continuo() -> None:
    import schedule

    config = carregar_json(CONFIG_DIR / "config.json")
    horario = config["boletim_email"]["horario_envio"]
    schedule.every().day.at(horario).do(executar_coleta)
    log.info("Modo continuo ativo. Coleta agendada todos os dias as %s. Pressione Ctrl+C para sair.", horario)
    while True:
        schedule.run_pending()
        time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser(description="Radar Fiscal TOTVS - coletor de noticias.")
    parser.add_argument("--continuo", action="store_true", help="Mantem o processo rodando e coleta todo dia no horario configurado.")
    parser.add_argument("--testar-fonte", metavar="ID", help="Testa uma unica fonte de config/sources.json e mostra o resultado no terminal.")
    parser.add_argument("--enviar-email", action="store_true", help="Forca o envio do boletim por e-mail mesmo fora do horario configurado.")
    args = parser.parse_args()

    if args.testar_fonte:
        testar_fonte(args.testar_fonte)
    elif args.continuo:
        executar_modo_continuo()
    else:
        executar_coleta(enviar_email_forcado=args.enviar_email)


if __name__ == "__main__":
    main()
