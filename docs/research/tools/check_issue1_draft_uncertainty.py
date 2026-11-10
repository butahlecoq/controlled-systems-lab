"""Check literal L04 draft/revision row offsets; never execute historical code."""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PREFIX = 'Minimax/Unconstrained for AaRC/'
SOURCES = {
    'draft_tex': (PREFIX+'Paper/Shorikov_Kalev_AiT.tex', 37412, '7dfcd12b5f946d459411ba7467d6a176d42ab33c20d56ce860fb8477c6ce956f'),
    'draft_pdf': (PREFIX+'Paper/Shorikov_Kalev_AiT.pdf', 455509, 'fae5f04fdc7686206d4fdca7dc9891bdf219ed60422a0b1a09e9fc015c449eb9'),
    'draft_png': (PREFIX+'Paper/first.png', 78648, 'bd528602ab944bc734d7847c7c9aa3106869581edb3896e1d0f3073ebf43da05'),
    'revised_tex': (PREFIX+'tex/Shorikov_Kalev_AиT_New.tex', 39881, '6bbbf3968862720c6ff90687428a8dac6fe4681998c697ac402650c07be2fa7c'),
    'published_pdf': (PREFIX+'Shorikov_Kalev_AиT_New.pdf', 390884, '6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f'),
    'revised_png': (PREFIX+'tex/first.png', 30938, '2c8cdc9865002ec0c5cebd3d940dbb824997714066cc9857798d5e6cf0e70293'),
    'nearby_fig': (PREFIX+'second.fig', 108014, 'f0ca6b5a7bf5297a0771284f46e811b04fbf0aba7b4597d23b4f37b95edeea5e'),
    'other_fig_copy': ('Minimax/Unconstrained/second.fig', 108014, 'f0ca6b5a7bf5297a0771284f46e811b04fbf0aba7b4597d23b4f37b95edeea5e'),
}
PIXEL_SHA256 = 'b2f29b56337fb046cade94b9699ebbeda017533b6dcfb513b121f9eeea3e38c0'


def vector(values):
    return list(map(Q, values))


def transition(x):
    return [x[0], x[1]-25*x[0], x[2], x[3]-25*x[2]]


def image(increments):
    x = vector([0, 0, 0, 0])
    for oxidizer, fuel in increments:
        x = transition(x)
        x[0] += oxidizer
        x[2] += fuel
    return x


def difference(left, right):
    return [a-b for a, b in zip(left, right)]


def norm(x):
    squared = sum((a-b)**2 for a, b in zip(x, vector([1200, 0, 450, 0])))
    with localcontext() as context:
        context.prec = 35
        context.rounding = ROUND_HALF_EVEN
        value = (Decimal(squared.numerator)/Decimal(squared.denominator)).sqrt()
    return dict(squared=str(squared), norm_decimal=str(value))


def certificate():
    older_nonlinear = vector(['1200.139', '-2.294', '450.406', '-16.254'])
    older_linear = vector(['1200.939', '-32.294', '451.206', '-46.254'])
    newer_nonlinear = vector(['1200.14', '-2.29', '450.41', '-16.25'])
    newer_linear = vector(['1201.14', '-27.29', '452.61', '-61.25'])
    older_increment = [(Q(1, 5), Q(1, 5))]*4
    newer_increment = [(Q(1+t, 10), Q(1+3*t, 10)) for t in range(4)]
    older_image, newer_image = image(older_increment), image(newer_increment)
    if older_image != difference(older_linear, older_nonlinear) or older_image != vector(['.8', '-30', '.8', '-30']):
        raise ValueError('draft row-offset identity differs')
    if newer_image != difference(newer_linear, newer_nonlinear) or newer_image != vector([1, -25, '2.2', -45]):
        raise ValueError('revised row-offset identity differs')
    literal = vector(['1182.074', '119560', '459.832', '45260'])
    b = vector(['20.073', 0, '-10.473', 0])
    for u in vector(['.6', '.6', '-.3', 0]):
        literal = [a+coefficient*u for a, coefficient in zip(transition(literal), b)]
    if literal != vector(['1200.1397', '-2.3275', '450.4063', '-16.2725']) or literal == older_nonlinear:
        raise ValueError('literal nominal terminal/discrepancy differs')
    encode = lambda x: [str(a) for a in x]
    return dict(
        schema='csl.issue1.draft-uncertainty-certificate/1',
        source_bindings={name:dict(papers_relative_path=p, bytes=size, sha256=h) for name, (p, size, h) in SOURCES.items()},
        older=dict(nonlinear_row=encode(older_nonlinear), linear_row=encode(older_linear),
                   applied_flow_corner=[encode(x) for x in older_increment], row_difference=encode(older_image),
                   reported_linear_cost='56.433', reported_nonlinear_cost='14.048',
                   linear_criterion=norm(older_linear), nonlinear_criterion=norm(older_nonlinear),
                   uncertainty_scope='Printed D has flow entries .2,-.2. A unit-box realization (+1,-1) gives these flow increments; numerical W1 is not instantiated in the draft example.'),
        revised=dict(nonlinear_row=encode(newer_nonlinear), linear_row=encode(newer_linear),
                     applied_flow_corner=[encode(x) for x in newer_increment], row_difference=encode(newer_image),
                     reported_linear_cost='67.12', reported_nonlinear_cost='14.05',
                     linear_criterion=norm(newer_linear), nonlinear_criterion=norm(newer_nonlinear),
                     uncertainty_scope='Printed unit flow D and bounds .1+.1*t / .1+.3*t; realization saturates positive flow error in both channels.'),
        literal_affine_nominal_terminal=encode(literal),
        literal_minus_older_nonlinear=encode(difference(literal, older_nonlinear)),
        recorded_private_image_identity=dict(size=[1481, 675], mode='RGB', decoded_pixel_sha256=PIXEL_SHA256,
                                             scope='Recorded private inspection; recomputed only with --pixel-check.'),
        scope='Exact arithmetic on displayed rows and one printed plan; conditional uncertainty-image identities, not a recovered MATLAB run, nonlinear integration, minimax search or historical reproduction.')


def verify_private(papers, pixel_check, figure_check):
    for path, size, expected in SOURCES.values():
        data = (papers/path).read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('private source identity differs: '+path)
    print('All eight private source byte identities match.', file=sys.stderr)
    if figure_check:
        verify_nearby_figure(papers)
    if not pixel_check:
        return
    if shutil.which('pdfimages') is None:
        raise ValueError('pixel check requires existing Poppler pdfimages')
    from PIL import Image  # Optional existing figure environment; no installation.
    with tempfile.TemporaryDirectory(prefix='issue1-pdf-image-') as temporary:
        root = Path(temporary)
        subprocess.run(['pdfimages', '-png', str(papers/SOURCES['draft_pdf'][0]), str(root/'image')], check=True)
        images = list(root.glob('image-*.png'))
        if len(images) != 1:
            raise ValueError('draft PDF image inventory differs')
        with Image.open(papers/SOURCES['draft_png'][0]) as original, Image.open(images[0]) as embedded:
            if original.mode != 'RGB' or embedded.mode != 'RGB' or original.size != (1481, 675) or embedded.size != original.size:
                raise ValueError('draft image mode/dimensions differ')
            pixels = original.tobytes()
            if pixels != embedded.tobytes() or hashlib.sha256(pixels).hexdigest() != PIXEL_SHA256:
                raise ValueError('draft embedded pixels differ')
    print('Draft PDF/source PNG decoded RGB pixels match exactly.', file=sys.stderr)


def verify_nearby_figure(papers):
    from scipy.io import loadmat  # Optional existing source-inspection environment.
    import numpy as np
    series = []
    def walk(value):
        if isinstance(value, dict):
            if value.get('type') == 'specgraph.stairseries':
                props = value['properties']
                x, y = (np.asarray(props[name]).reshape(-1) for name in ('XData', 'YData'))
                series.append((len(x), float(x[0]), float(y[0]), float(x[-1]), float(y[-1])))
            for name, child in value.items():
                if name != 'properties':
                    walk(child)
        elif isinstance(value, (list, np.ndarray)):
            for child in value:
                walk(child)
    walk(loadmat(papers/SOURCES['nearby_fig'][0], simplify_cells=True))
    expected = [(1001, 29.375148491328105, 302.0, 30.0, 6.0345294958112055),
                (1001, 20.399408674533408, 207.0, 20.0, 4.473053442902353)]
    if series != expected:
        raise ValueError('nearby figure stored-data identity differs')
    print('Both byte-identical nearby FIG copies contain the recorded unrelated 30/20-flow case.', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-papers', type=Path)
    parser.add_argument('--pixel-check', action='store_true')
    parser.add_argument('--figure-check', action='store_true')
    parser.add_argument('--verify-record', type=Path)
    args = parser.parse_args()
    if (args.pixel_check or args.figure_check) and args.private_papers is None:
        parser.error('--pixel-check/--figure-check require --private-papers')
    if args.private_papers is not None:
        verify_private(args.private_papers, args.pixel_check, args.figure_check)
    result = certificate()
    if args.verify_record is not None:
        if json.loads(args.verify_record.read_text()) != result:
            raise ValueError('saved literal certificate differs')
        print('Literal Fraction certificate matches the saved record.')
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
