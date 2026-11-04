"""Fabrique de mini-modèles ONNX pour les tests (sortie CONSTANTE : valide la plomberie, pas un vrai YOLO)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

# Sortie YOLOv8 : lignes = cx, cy, w, h, score_classe0, score_classe1 ; colonnes = candidats.
#            A      A'(doublon)  B       C(faible)  D(classe 1, sur A)
COLUMNS = np.array(
    [
        [32.0, 33.0, 16.0, 48.0, 32.0],  # cx
        [32.0, 33.0, 40.0, 10.0, 32.0],  # cy
        [16.0, 16.0, 8.0, 8.0, 16.0],  # w
        [16.0, 16.0, 8.0, 8.0, 16.0],  # h
        [0.90, 0.80, 0.70, 0.05, 0.05],  # classe 0 « enemy »
        [0.05, 0.05, 0.10, 0.04, 0.60],  # classe 1 « ally »
    ],
    dtype=np.float32,
)
LABELS = ("enemy", "ally")


def make_constant_yolo_model(
    path: Path, columns: np.ndarray = COLUMNS, input_shape: list[str | int | None] | None = None
) -> Path:
    out = columns[np.newaxis].astype(np.float32)
    constant = helper.make_node("Constant", [], ["output0"], value=numpy_helper.from_array(out))
    shape = input_shape or [1, 3, 64, 64]
    graph = helper.make_graph(
        [constant],
        "constant_yolo",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, shape)],
        [helper.make_tensor_value_info("output0", TensorProto.FLOAT, list(out.shape))],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 10
    onnx.save(model, path)
    return path
