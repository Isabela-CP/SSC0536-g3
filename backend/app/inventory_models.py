"""Modelos Pydantic derivados do contrato, incluindo as seções opcionais extensas.

A validação JSON Schema anterior à conversão preserva as regras do OpenAPI
(null explícito, uniqueItems e minProperties), sem coerções permissivas.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from pydantic_core import PydanticCustomError


CONTRACT = json.loads((Path(__file__).resolve().parents[2] /
                       "contratos_api_oto/openapi.json").read_text(encoding="utf-8"))
SCHEMAS = CONTRACT["components"]["schemas"]


def flatten(schema: dict) -> dict:
    if "$ref" in schema:
        return flatten(SCHEMAS[schema["$ref"].rsplit("/", 1)[-1]])
    if "allOf" not in schema:
        return schema
    result = {"type": "object", "properties": {}, "required": []}
    for part in schema["allOf"]:
        part = flatten(part)
        result["properties"].update(part.get("properties", {}))
        result["required"].extend(part.get("required", []))
    return result


class ContractModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def validate_contract(cls, value):
        if isinstance(value, cls):
            return value
        schema = cls.model_config["json_schema_extra"]
        validator = Draft202012Validator({**schema, "components": CONTRACT["components"]},
                                        format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(value), key=lambda error: str(list(error.path)))
        if errors:
            error = errors[0]
            path = ".".join(map(str, error.path))
            if error.validator == "required":
                missing = next(key for key in error.validator_value if key not in error.instance)
                path = ".".join(filter(None, (path, missing)))
            raise PydanticCustomError("contract", "{field}: {issue}",
                                      {"field": path or "body", "issue": error.message})
        return value


def field_type(schema: dict, name: str):
    if "$ref" in schema:
        reference = schema["$ref"].rsplit("/", 1)[-1]
        target = flatten(SCHEMAS[reference])
        return contract_model(reference) if target.get("type") == "object" else field_type(target, reference)
    if "oneOf" in schema:
        return Union[tuple(field_type(part, name) for part in schema["oneOf"])]
    kind = schema.get("type")
    if isinstance(kind, list):
        return Union[tuple(field_type({**schema, "type": entry}, name) for entry in kind)]
    if "enum" in schema:
        return Literal[tuple(schema["enum"])]
    if kind == "null":
        return type(None)
    if kind == "object":
        return build_model(name, schema)
    if kind == "array":
        return list[field_type(schema["items"], name + "Item")]
    if kind == "string":
        return {"date": date, "date-time": datetime, "time": time, "uuid": UUID}.get(schema.get("format"), str)
    return {"integer": int, "number": float, "boolean": bool}.get(kind, Any)


def build_model(name: str, schema: dict):
    fields = {}
    for key, value in schema.get("properties", {}).items():
        constraints = {target: value[source] for source, target in (
            ("minLength", "min_length"), ("maxLength", "max_length"),
            ("minimum", "ge"), ("maximum", "le"), ("pattern", "pattern"),
        ) if source in value}
        annotation = field_type(value, name + key.title())
        if constraints:
            annotation = Annotated[annotation, Field(**constraints)]
        default = ... if key in schema.get("required", []) else value.get("default", None)
        fields[key] = (annotation, default)
    config = ConfigDict(extra="forbid" if schema.get("additionalProperties") is False else "allow",
                        json_schema_extra=schema)
    base = type(name + "Base", (ContractModel,), {"model_config": config})
    return create_model(name, __base__=base, **fields)


@lru_cache
def contract_model(name: str):
    return build_model(name, flatten(SCHEMAS[name]))


EstablishmentCreate = contract_model("EstabelecimentoCreate")
EstablishmentUpdate = contract_model("EstabelecimentoUpdate")
Establishment = contract_model("Estabelecimento")
DocumentCreate = contract_model("DocumentoControleCreate")
DocumentUpdate = contract_model("DocumentoControleUpdate")
Document = contract_model("DocumentoControle")
Inactivation = build_model("Inactivation", CONTRACT["paths"][
    "/estabelecimentos/{id_estabelecimento}/inativacao"]["post"][
        "requestBody"]["content"]["application/json"]["schema"])
