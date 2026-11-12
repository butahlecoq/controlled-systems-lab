"""Independent checks of recorded native physical-region membership witnesses."""
from __future__ import annotations

import numpy as np


def validate_regions(response, state_dimension, horizon, *, atol=1e-7, rtol=1e-8):
    history = np.asarray(response['history'], dtype=float)
    regions, witnesses = response['regions'], response['reduced_argmin']['region_factors']
    if len(regions) != horizon + 1 or len(witnesses) != len(regions):
        raise ValueError('native fixed-tail response must retain every physical stage and witness')
    checks = []
    for stage, (region, witness) in enumerate(zip(regions, witnesses)):
        if region['stage'] != stage or region['family'] != response['family']:
            raise ValueError('native physical region identity or stage differs')
        x = history[stage * state_dimension:(stage + 1) * state_dimension]
        passed = True
        for key, bounds, equality in (('inequalities', 'upper_bounds', False),
                                       ('equalities', 'equality_values', True)):
            rows, rhs = region['reference'][key], np.asarray(region['reference'][bounds], dtype=float)
            if not rows:
                if len(rhs):
                    raise ValueError('native physical reference bounds differ from row count')
                continue
            matrix = np.asarray(rows, dtype=float)
            if matrix.shape != (len(rhs), state_dimension) or not np.isfinite(matrix).all() or not np.isfinite(rhs).all():
                raise ValueError('malformed native physical reference')
            lhs = matrix @ x
            residual = abs(lhs - rhs) if equality else np.maximum(lhs - rhs, 0)
            passed &= bool(np.all(residual <= atol + rtol * np.maximum(abs(lhs), abs(rhs))))
        member = region['membership']
        if 'center' in member:
            center, factor = np.asarray(member['center']), np.asarray(member['factor'])
            if center.shape != (state_dimension,) or factor.ndim != 2 or factor.shape[0] != state_dimension:
                raise ValueError('native physical factor dimensions differ')
            w = np.asarray(witness if witness else [0] * factor.shape[1])
            if w.shape != (factor.shape[1],) or not all(np.isfinite(value).all() for value in (center, factor, w)):
                raise ValueError('native physical factor witness is malformed')
            norm = member['factor_domain_norm']
            if (norm, member['support_norm']) not in {('linf', 'l1'), ('l2', 'l2')}:
                raise ValueError('native support and factor-domain norms differ')
            bound = np.linalg.norm(w) if norm == 'l2' else np.max(abs(w), initial=0)
            reconstructed = center + factor @ w
            passed &= bool(bound <= 1 + atol and np.all(abs(x - reconstructed) <= atol + rtol * np.maximum(abs(x), abs(reconstructed))))
        checks.append({'stage': stage, 'passed': passed})
    return {'accepted': all(row['passed'] for row in checks), 'stages': checks}
