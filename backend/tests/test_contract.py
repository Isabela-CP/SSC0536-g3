"""Integridade do OpenAPI estendido durante a integração final."""
import json
import re
from app import main


def test_security_and_path_references_are_defined():
    spec=json.loads(main.OPENAPI_FILE.read_text())
    schemes=spec['components']['securitySchemes']
    for path,methods in spec['paths'].items():
        for method,operation in methods.items():
            if not isinstance(operation,dict) or 'responses' not in operation:continue
            for requirement in operation.get('security',spec.get('security',[])):
                assert set(requirement).issubset(schemes),(path,method,requirement)
            parameters = [*methods.get('parameters', []), *operation.get('parameters', [])]
            resolved = [spec['components']['parameters'][p['$ref'].rsplit('/', 1)[1]] if '$ref' in p else p for p in parameters]
            names = {p['name'] for p in resolved if p['in'] == 'path'}
            assert set(re.findall(r'\{([^}]+)\}',path)).issubset(names),(path,method)
