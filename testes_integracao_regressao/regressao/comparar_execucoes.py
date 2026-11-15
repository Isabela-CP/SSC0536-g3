"""Compara duas execuções (JUnit XML do pytest ou do node --test) caso a caso.

Uso: python comparar_execucoes.py <base.xml> <atual.xml> [--json saida.json]
Sai com código 1 se houver regressão: caso aprovado (ou falha esperada) na base que falha na atual.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter

ORDEM = ["aprovado", "xfail", "pulado", "falhou", "erro"]


def resultados(caminho: str) -> dict[str, str]:
    saida, vistos = {}, Counter()
    for caso in ET.parse(caminho).iter("testcase"):
        chave = f"{caso.get('classname', '')}::{caso.get('name')}".lstrip(":")
        vistos[chave] += 1
        if vistos[chave] > 1:            # títulos repetidos (comum no node --test): numera as ocorrências
            chave += f" #{vistos[chave]}"
        if caso.find("failure") is not None:
            estado = "falhou"
        elif caso.find("error") is not None:
            estado = "erro"
        elif (pulado := caso.find("skipped")) is not None:
            estado = "xfail" if "xfail" in (pulado.get("type", "") + pulado.get("message", "")) else "pulado"
        else:
            estado = "aprovado"
        saida[chave] = estado
    return saida


def comparar(base: dict, atual: dict) -> dict:
    comuns = base.keys() & atual.keys()
    mudancas = sorted((k, base[k], atual[k]) for k in comuns if base[k] != atual[k])
    regressoes = [m for m in mudancas if m[1] in ("aprovado", "xfail") and m[2] in ("falhou", "erro")]
    return {"comuns": len(comuns), "base": dict(Counter(base.values())), "atual": dict(Counter(atual.values())),
            "mudancas": mudancas, "regressoes": regressoes,
            "so_na_base": sorted(base.keys() - atual.keys()), "so_na_atual": sorted(atual.keys() - base.keys())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("atual")
    parser.add_argument("--json")
    args = parser.parse_args()
    r = comparar(resultados(args.base), resultados(args.atual))
    fmt = lambda c: ", ".join(f"{k} {c[k]}" for k in ORDEM if k in c)  # noqa: E731
    print(f"casos em comum: {r['comuns']}")
    print(f"base : {fmt(r['base'])}")
    print(f"atual: {fmt(r['atual'])}")
    print(f"mudanças de resultado: {len(r['mudancas'])} | regressões: {len(r['regressoes'])}")
    for chave, antes, depois in r["mudancas"]:
        print(f"  {'REGRESSÃO' if (chave, antes, depois) in r['regressoes'] else 'mudança  '} {chave}: {antes} -> {depois}")
    if r["so_na_atual"]:
        print(f"casos novos na atual: {len(r['so_na_atual'])}")
    if r["so_na_base"]:
        print(f"casos só na base: {len(r['so_na_base'])}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as arquivo:
            json.dump(r, arquivo, ensure_ascii=False, indent=2)
    return 1 if r["regressoes"] else 0


if __name__ == "__main__":
    sys.exit(main())
