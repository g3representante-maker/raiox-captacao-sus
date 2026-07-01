#!/usr/bin/env python3
"""
Detecta propostas de custeio MAC/PAP recém-pagas nos municípios da CONTROLADORIA
(planilha Google) e prepara um resumo para envio por e-mail.

Estado persistido em estado_pagamentos.json (nuProposta -> vlPago já visto).
Escreve alerta_email.txt (assunto+corpo) e imprime TEM_NOVOS=1/0.
Uso no CI: os secrets de SMTP enviam o e-mail só quando TEM_NOVOS=1.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fontes import consulta_fns_proposta as cf

CTRL_URL = ("https://docs.google.com/spreadsheets/d/e/2PACX-1vTMcZpgiHbci8FynfSa"
            "Q4wojiPxplxmSKbzhrwoAz1kE9L6bXiaUyWWAZ16vtq9ZBBObHd0xGTdaf6w/pub?output=csv")
ANOS = [2025, 2026]
TIPOS = ["CUSTEIO MAC", "CUSTEIO PAP"]
BASE = Path(__file__).parent
ESTADO = BASE / "estado_pagamentos.json"
EMAIL = BASE / "alerta_email.txt"


def _reais(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ler_controladoria():
    txt = urllib.request.urlopen(CTRL_URL, timeout=30).read().decode("utf-8")
    linhas = [l for l in txt.splitlines() if l.strip()]
    hdr = [h.strip().lower() for h in linhas[0].split(",")]
    iI = next((i for i, h in enumerate(hdr) if h.startswith("ibge")), 0)
    iM = next((i for i, h in enumerate(hdr) if h.startswith("municipio")), 1)
    out = []
    for l in linhas[1:]:
        c = l.split(",")
        ibge = c[iI].strip()[:6] if iI < len(c) else ""
        nome = c[iM].strip() if iM < len(c) else ""
        if ibge:
            out.append((ibge, nome))
    return out


def main():
    muns = ler_controladoria()
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    primeira_vez = not ESTADO.exists()
    novos = []
    for ibge, nome in muns:
        for ano in ANOS:
            for tp in TIPOS:
                try:
                    itens = cf.consultar_individuais(ibge, ano, tp)
                except Exception:
                    itens = []
                for it in itens:
                    nu = str(it.get("nuProposta") or "")
                    if not nu:
                        continue
                    pago = float(it.get("vlPago") or 0)
                    ant = float(estado.get(nu, 0))
                    if pago > ant and pago > 0 and not primeira_vez:
                        novos.append({
                            "mun": nome, "uf": it.get("sgUf", ""), "ibge": ibge,
                            "nu": nu, "bloco": tp, "ano": ano,
                            "pago": pago, "delta": pago - ant,
                            "proposta": float(it.get("vlProposta") or 0),
                        })
                    estado[nu] = pago

    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=0))

    if novos:
        linhas = ["ALERTA — Propostas de custeio MAC/PAP PAGAS", ""]
        total = 0.0
        for n in sorted(novos, key=lambda x: -x["delta"]):
            total += n["delta"]
            linhas.append(f"• {n['mun']}/{n['uf']} — {n['bloco']} {n['ano']}")
            linhas.append(f"    Proposta {n['nu']} · pago agora {_reais(n['pago'])} (novo: {_reais(n['delta'])})")
            linhas.append(f"    Detalhe: https://consultafns.saude.gov.br/#/proposta/{n['nu']}/detalhe")
        linhas += ["", f"Total de novos pagamentos: {_reais(total)}",
                   "", "Painel: https://g3healthservice.github.io/raiox-captacao-sus/",
                   "— Robô Raio-X SUS · G3 Health Service"]
        EMAIL.write_text("\n".join(linhas), encoding="utf-8")
        print(f"TEM_NOVOS=1  ({len(novos)} pagamento(s))")
    else:
        if EMAIL.exists():
            EMAIL.unlink()
        motivo = "primeira execução (baseline registrado)" if primeira_vez else "sem novos pagamentos"
        print(f"TEM_NOVOS=0  ({motivo}; {len(muns)} municípios monitorados)")


if __name__ == "__main__":
    main()
