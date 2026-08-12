import json
import os

class ArchitectureGraph:
    def __init__(self, schemas_dir):
        self.expected_edges = {}
        with open(os.path.join(schemas_dir, "expected_architecture.json"), "r") as f:
            self.expected_edges = json.load(f)

    def evaluate_trace(self, spans, mode="normal"):
        nodes_hit = set()
        edges_hit = set()
        for s in spans:
            src = s.get("payload", {}).get("source")
            dst = s.get("payload", {}).get("dest")
            if src: nodes_hit.add(src)
            if dst: nodes_hit.add(dst)
            if src and dst:
                edges_hit.add((src, dst))
                
        missing_edges = []
        unexpected_edges = []
        forbidden_edges = []
        
        scenario_edges = self.expected_edges.get(mode, self.expected_edges.get("normal", {}))
        
        expected_total = 0
        observed_total = len(edges_hit)
        
        # Check required edges
        for src, dests in scenario_edges.items():
            for dst, edge_type in dests.items():
                if edge_type == "REQUIRED":
                    expected_total += 1
                    # A required edge must be in edges_hit
                    if (src, dst) not in edges_hit:
                        missing_edges.append(f"{src} -> {dst}")
                elif edge_type == "FORBIDDEN":
                    if (src, dst) in edges_hit:
                        forbidden_edges.append(f"{src} -> {dst}")
                elif edge_type == "INACTIVE_BY_SCENARIO":
                    if (src, dst) in edges_hit:
                        unexpected_edges.append(f"{src} -> {dst} (was INACTIVE_BY_SCENARIO)")

        # Check unexpected edges
        for (src, dst) in edges_hit:
            dests = scenario_edges.get(src, {})
            if dst not in dests:
                unexpected_edges.append(f"{src} -> {dst}")
                
        return {
            "nodes_hit": list(nodes_hit),
            "missing_edges": missing_edges,
            "unexpected_edges": unexpected_edges,
            "forbidden_edges": forbidden_edges,
            "expected_total": expected_total,
            "observed_total": observed_total
        }
