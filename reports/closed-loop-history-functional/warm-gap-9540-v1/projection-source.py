"""Saved-set rendering functions extracted without modification from source9540 plot_feedback_history.py."""
import math
import itertools
import numpy as np

def axis_bounds(member, dimension):
    lower = [float("-inf")] * dimension
    upper = [float("inf")] * dimension
    for rows, bounds, equality in ((member["inequalities"], member["upper_bounds"], False),
                                   (member["equalities"], member["equality_values"], True)):
        if len(rows) != len(bounds):
            raise ValueError("box row count differs from bounds")
        for row, bound in zip(rows, bounds):
            active = [i for i, value in enumerate(row) if value != 0]
            if len(row) != dimension or len(active) != 1:
                raise ValueError("box membership is not axis-aligned in full state space")
            i = active[0]
            value = bound / row[i]
            if row[i] > 0 or equality:
                upper[i] = min(upper[i], value)
            if row[i] < 0 or equality:
                lower[i] = max(lower[i], value)
    import math
    if any(not math.isfinite(v) for v in lower + upper) or any(a > b for a,b in zip(lower, upper)):
        raise ValueError("box does not have finite ordered bounds")
    return lower, upper

def convex_boundary(points):
    points = sorted(set(map(tuple, points)))
    if len(points) < 3:
        return points
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    halves = []
    for ordered in (points, reversed(points)):
        half = []
        for point in ordered:
            while len(half) > 1 and cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return halves[0] + halves[1]

def h_polygon(member):
    A = np.asarray(member["inequalities"], dtype=float).reshape(-1, 2)
    b = np.asarray(member["upper_bounds"], dtype=float)
    E = np.asarray(member["equalities"], dtype=float).reshape(-1, 2)
    e = np.asarray(member["equality_values"], dtype=float)
    if len(A) != len(b) or len(E) != len(e) or not all(np.isfinite(v).all() for v in (A, b, E, e)):
        raise ValueError("invalid finite H rows")
    rank = np.linalg.matrix_rank(E) if len(E) else 0
    if rank == 0:
        angles = sorted(math.atan2(row[1], row[0]) for row in A if np.any(row))
        if not angles or max(y-x for x, y in zip(angles, angles[1:]+[angles[0]+2*math.pi])) >= math.pi:
            raise ValueError("bounded H polygon required")
    elif rank == 1:
        normal = next(row for row in E if np.any(row))
        slopes = A @ np.array([-normal[1], normal[0]])
        if not (np.any(slopes > 0) and np.any(slopes < 0)):
            raise ValueError("bounded H segment required")
    rows = np.concatenate((A, E))
    rhs = np.concatenate((b, e))
    points = []
    for i, j in itertools.combinations(range(len(rows)), 2):
        pair = rows[[i, j]]
        if np.linalg.det(pair) == 0:
            continue
        point = np.linalg.solve(pair, rhs[[i, j]])
        if (np.isfinite(point).all() and np.all(A @ point <= b + 1e-9*(1+np.abs(b)))
                and np.all(np.abs(E @ point-e) <= 1e-9*(1+np.abs(e)))):
            points.append(point)
    if not points:
        raise ValueError("no finite vertices of the bounded H set")
    return convex_boundary(points)

def project_h(member, dimension, first, second):
    from scipy.optimize import linprog
    A = np.asarray(member["inequalities"], dtype=float).reshape(-1, dimension)
    E = np.asarray(member["equalities"], dtype=float).reshape(-1, dimension)
    b = np.asarray(member["upper_bounds"], dtype=float)
    e = np.asarray(member["equality_values"], dtype=float)
    if len(A) != len(b) or len(E) != len(e) or not all(np.isfinite(v).all() for v in (A, b, E, e)):
        raise ValueError("invalid finite full-state H rows")
    def support(direction):
        objective = np.zeros(dimension)
        objective[[first, second]] = -np.asarray(direction)
        objective /= max(np.max(np.abs(objective)), 1e-300)
        result = linprog(objective, A_ub=A if len(A) else None, b_ub=b if len(A) else None,
                         A_eq=E if len(E) else None, b_eq=e if len(E) else None,
                         bounds=[(None, None)]*dimension, method="highs")
        if not result.success:
            raise ValueError("bounded feasible H projection required: " + result.message)
        return result.x[[first, second]]
    points = np.asarray([support(d) for d in ((1, 0), (-1, 0), (0, 1), (0, -1))])
    origin = np.min(points, axis=0)
    scales = np.ptp(points, axis=0)
    scales[scales == 0] = 1
    normalized = [tuple(p) for p in (points-origin)/scales]
    for _ in range(128):
        hull = convex_boundary(normalized)
        if len(hull) == 2:
            edge = np.asarray(hull[1])-hull[0]
            normal = np.array([edge[1], -edge[0]]) / np.linalg.norm(edge)
            extra = []
            for direction in (normal, -normal):
                point = (support(direction/scales)-origin)/scales
                if abs(normal @ (point-hull[0])) > 1e-8:
                    extra.append(tuple(point))
            if extra:
                normalized.extend(extra)
                continue
        if len(hull) < 3:
            return {"points": (np.asarray(hull)*scales+origin).tolist(),
                    "method": "numerical full-state LP projection", "normalized_support_tolerance": 1e-8}
        additions = []
        for a, b0 in zip(hull, hull[1:]+hull[:1]):
            edge = np.asarray(b0)-a
            direction = np.array([edge[1], -edge[0]])
            direction /= np.linalg.norm(direction)
            point = (support(direction/scales)-origin)/scales
            if direction @ (point-a) > 1e-8:
                additions.append(tuple(point))
        if not additions:
            return {"points": (np.asarray(hull)*scales+origin).tolist(),
                    "method": "numerical full-state LP projection", "normalized_support_tolerance": 1e-8}
        normalized.extend(additions)
        if len(normalized) > 2048:
            break
    raise ValueError("H projection rendering quota exhausted")

def project_member(member, dimension, first, second):
    if first == second or not 0 <= first < dimension or not 0 <= second < dimension:
        raise ValueError("distinct physical projection coordinates required")
    kind = member["kind"]
    if kind == "h":
        try:
            lower, upper = axis_bounds(member, dimension)
        except ValueError:
            if dimension == 2:
                points = np.asarray(h_polygon(member))[:, [first, second]].tolist()
                return {"points": points, "method": "numerical 2D H boundary intersections"}
            return project_h(member, dimension, first, second)
        return {"points": [[lower[first], lower[second]], [upper[first], lower[second]],
                            [upper[first], upper[second]], [lower[first], upper[second]]],
                "method": "full-state axis H projection"}
    if kind not in {"zonotope", "ellipsoid"}:
        raise ValueError("unknown saved set representation")
    center = np.asarray(member["center"], dtype=float)
    factor = np.asarray(member["factor"], dtype=float)
    if (center.shape != (dimension,) or factor.shape != (dimension, member["factor_count"])
            or not np.isfinite(center).all() or not np.isfinite(factor).all()):
        raise ValueError("invalid full-state center or factor")
    center, factor = center[[first, second]], factor[[first, second]]
    if not factor.size:
        return {"points": [center.tolist()], "method": "zero-factor point projection"}
    if kind == "zonotope":
        generators = []
        for g in factor.T:
            if not np.any(g):
                continue
            if g[1] < 0 or (g[1] == 0 and g[0] < 0):
                g = -g
            generators.append(g)
        generators.sort(key=lambda g: math.atan2(g[1], g[0]))
        current = center-sum(generators, np.zeros(2))
        points = [current.tolist()]
        for sign in (1, -1):
            for g in generators:
                current = current + sign*2*g
                points.append(current.tolist())
        return {"points": points, "method": "projected generator boundary"}
    left, singular, _ = np.linalg.svd(factor, full_matrices=True)
    radii = np.zeros(2)
    radii[:len(singular)] = singular
    angles = np.linspace(0, 2*math.pi, 129)
    points = center[:, None] + (left*radii) @ np.array([np.cos(angles), np.sin(angles)])
    return {"points": points.T.tolist(), "method": "projected ellipsoid factor",
            "rendering_segments": 128}
