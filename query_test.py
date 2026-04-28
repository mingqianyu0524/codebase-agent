from src.cbm_client import CBMClient

c = CBMClient()
q = (
    "MATCH (caller)-[:CALLS]->(callee) "
    "WHERE callee.name CONTAINS 'LateInhibition' "
    "RETURN caller.name, caller.file_path, callee.name LIMIT 20"
)
r = c.query_graph(q)
import pprint
pprint.pp(r)
