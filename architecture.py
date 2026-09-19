"""Static dependency gate for the flat Python projection in src/.

x0 is reserved and empty. This table is the single layer assignment; filenames
need not encode it yet. Includes function-local imports, rejects unknown modules
and explicit dynamic imports. Not an analyzer for arbitrary Python execution.
"""
import ast
from pathlib import Path

LAYERS = {
    '__init__': 1, 'build': 1, 'kernel': 1, 'store': 1, 'canonical': 1,
    'checks': 2, 'compiler': 2, 'boolean': 2, 'properties': 2,
    'certificate': 3, 'experiment': 3, 'records': 3, 'facts': 3, 'case': 3, 'lab': 3,
    'policy': 4, 'bundle': 4, 'search': 4, 'invariants': 4, 'lineage': 4, 'labtask': 4, 'machine': 4,
    'artifact': 5, 'composition': 5, 'evidence': 5,
    'cli': 6, '__main__': 6,
}


def check_sources(sources, layers=LAYERS):
    errors = []
    if set(sources) != set(layers):
        errors.append('module table mismatch: ' + repr(sorted(set(sources) ^ set(layers))))
    if any(type(layer) is not int or layer < 1 for layer in layers.values()):
        errors.append('x0 is reserved; all current modules must have layer >= 1')
    graph = {name: set() for name in sources}
    for name, source in sources.items():
        for node in ast.walk(ast.parse(source, filename=name)):
            targets = []
            if isinstance(node, ast.ImportFrom):
                if not node.level and node.module and (node.module == 'src' or node.module.startswith('src.')):
                    errors.append(name + ': use stargate imports, not the src directory name')
                    continue
                if node.level:
                    if node.level != 1:
                        errors.append(name + ': relative import escapes package')
                        continue
                    if node.module:
                        targets = [node.module.split('.')[0]]
                    else:
                        targets = [a.name if a.name in sources else '__init__' for a in node.names]
                        for alias in node.names:
                            if alias.name not in sources and alias.name not in ('KELVIN', 'CONTRACT_STATUS'):
                                errors.append(name + ': unknown package export ' + alias.name)
                elif node.module == 'stargate':
                    targets = [a.name if a.name in sources else '__init__' for a in node.names]
                    for alias in node.names:
                        if alias.name not in sources and alias.name not in ('KELVIN', 'CONTRACT_STATUS'):
                            errors.append(name + ': unknown package export ' + alias.name)
                elif node.module and node.module.startswith('stargate.'):
                    targets = [node.module.split('.')[1]]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == 'src' or alias.name.startswith('src.'):
                        errors.append(name + ': use stargate imports, not the src directory name')
                        continue
                    if alias.name == 'stargate':
                        targets.append('__init__')
                    elif alias.name.startswith('stargate.'):
                        targets.append(alias.name.split('.')[1])
            elif isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name) and node.func.id == '__import__' or
                    isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module'):
                errors.append(name + ': dynamic import requires an explicit architecture decision')
            for target in targets:
                if target not in sources:
                    errors.append(name + ': unknown module ' + target)
                    continue
                graph[name].add(target)
                if name in layers and target in layers and layers[target] > layers[name]:
                    errors.append(f'upward import: {name} -> {target}')
    active, done = set(), set()
    def visit(name, path):
        if name in active:
            errors.append('cycle: ' + ' -> '.join(path + [name])); return
        if name in done:
            return
        active.add(name)
        for target in sorted(graph[name]):
            visit(target, path + [name])
        active.remove(name); done.add(name)
    for name in sorted(graph):
        visit(name, [])
    return graph, errors


def inspect(root):
    return check_sources({p.stem: p.read_text() for p in Path(root).glob('*.py')})


if __name__ == '__main__':
    graph, errors = inspect(Path(__file__).resolve().parent / 'src')
    for name in sorted(graph, key=lambda n: (LAYERS.get(n, 99), n)):
        print(f'x{LAYERS.get(name, "?")} {name}: ' + ', '.join(sorted(graph[name])))
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
