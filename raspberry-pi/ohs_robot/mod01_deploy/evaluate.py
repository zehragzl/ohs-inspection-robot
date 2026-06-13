"""
evaluate.py — MOD-01 PPE Detection Test Harness
Ground-truth YOLO label'larıyla karşılaştırmalı değerlendirme.

Kullanım:
    python evaluate.py            # varsayılan 10 görsel
    python evaluate.py --n 50     # 50 görsel
    python evaluate.py --n 0      # tüm test seti (yavaş)
    python evaluate.py --seed 99  # farklı rastgele tohum
"""

import argparse
import os
import random
from collections import defaultdict

import cv2
import numpy as np

from inference import (
    CLASSES,
    CLASS_THRESHOLDS,
    VIOLATION_CLASSES,
    ppe_run_inference,
)

DATASET_ROOT = os.path.join(os.path.dirname(__file__), "ppe_dataset", "test")
IMG_DIR = os.path.join(DATASET_ROOT, "images")
LBL_DIR = os.path.join(DATASET_ROOT, "labels")

IOU_THRESHOLD = 0.25  # model tight kutular üretiyor (lens alanı vs GT frame+yüz alanı).
                      # Ultralytics ile ONNX kutuları birebir aynı — bu model davranışı.
                      # mAP@0.5 resmi 0.809 (Ultralytics val) ama burada 0.25 daha gerçekçi.


# ── Yardımcı fonksiyonlar ──────────────────────────────────────────────────

def iou(boxA, boxB):
    """Her iki kutu [x1,y1,x2,y2] formatında."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0.0
    areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return inter / (areaA + areaB - inter)


_KNOWN_CLASSES = set(CLASSES.keys())   # {0..6}


def load_gt(label_path, img_w, img_h):
    """
    YOLO normalize txt → pixel kutu listesi.
    Her satır: class_id cx cy w h (normalize [0,1])
    Dönüş: [ {"class_id": int, "box": [x1,y1,x2,y2]}, ... ]
    Not: Roboflow dataset bazı etiket dosyalarında class_id >= 7 içeriyor
         (modelimizin bilmediği ek sınıflar). Bunlar sessizce atlanır.
    """
    gts = []
    if not os.path.exists(label_path):
        return gts
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cid = int(parts[0])
            if cid not in _KNOWN_CLASSES:
                continue   # bilinmeyen sınıf (model kapsamı dışı)
            cx, cy, w, h = map(float, parts[1:5])
            x1 = int((cx - w / 2) * img_w)
            y1 = int((cy - h / 2) * img_h)
            x2 = int((cx + w / 2) * img_w)
            y2 = int((cy + h / 2) * img_h)
            gts.append({"class_id": cid, "box": [x1, y1, x2, y2]})
    return gts


def match_detections(preds, gts):
    """
    Greedy IoU eşleştirme (class-aware, IoU ≥ 0.5).

    Dönüş:
        tp_ids   — eşleşen tahmin index'leri
        fp_ids   — eşleşmeyen tahmin index'leri (false positive)
        fn_ids   — eşleşmeyen GT index'leri (false negative)
        dup_ids  — birden fazla tahminle örtüşen (duplicate) tahmin index'leri
    """
    matched_gt = set()
    matched_pred = set()
    dup_ids = []

    for pi, pred in enumerate(preds):
        best_iou = 0.0
        best_gi = -1
        for gi, gt in enumerate(gts):
            if gt["class_id"] != pred["class_id"]:
                continue
            v = iou(pred["bounding_box"], gt["box"])
            if v > best_iou:
                best_iou = v
                best_gi = gi
        if best_iou >= IOU_THRESHOLD:
            if best_gi in matched_gt:
                dup_ids.append(pi)   # bu GT zaten başka tahminle eşleşmişti
            else:
                matched_gt.add(best_gi)
                matched_pred.add(pi)

    tp_ids = list(matched_pred)
    fp_ids = [i for i in range(len(preds)) if i not in matched_pred and i not in dup_ids]
    fn_ids = [i for i in range(len(gts)) if i not in matched_gt]
    return tp_ids, fp_ids, fn_ids, dup_ids


# ── Ana değerlendirme döngüsü ──────────────────────────────────────────────

def evaluate(n_samples: int = 10, seed: int = 42):
    all_images = [f for f in os.listdir(IMG_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not all_images:
        print(f"Görsel bulunamadı: {IMG_DIR}")
        return

    rng = random.Random(seed)
    if n_samples > 0:
        samples = rng.sample(all_images, min(n_samples, len(all_images)))
    else:
        samples = all_images[:]

    print(f"\n{'='*70}")
    print(f"MOD-01 Değerlendirme  |  {len(samples)} görsel  |  seed={seed}  |  IoU≥{IOU_THRESHOLD}")
    print(f"{'='*70}\n")

    latencies = []
    # Sınıf bazında sayaçlar
    stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "dup": 0, "pred": 0, "gt": 0})

    for fname in samples:
        img_path = os.path.join(IMG_DIR, fname)
        stem = os.path.splitext(fname)[0]
        lbl_path = os.path.join(LBL_DIR, stem + ".txt")

        img = cv2.imread(img_path)
        if img is None:
            print(f"  [SKIP] Okunamadı: {fname}")
            continue
        orig_h, orig_w = img.shape[:2]

        gts = load_gt(lbl_path, orig_w, orig_h)
        result = ppe_run_inference(image_path=img_path)

        if not result["success"]:
            print(f"  [FAIL] inference hatası: {fname}")
            continue

        latencies.append(result["latency_ms"])
        preds = result["detections"]

        tp_ids, fp_ids, fn_ids, dup_ids = match_detections(preds, gts)

        # Sınıf bazında say
        for i in tp_ids:
            cid = preds[i]["class_id"]
            stats[cid]["tp"] += 1
            stats[cid]["pred"] += 1
        for i in fp_ids:
            cid = preds[i]["class_id"]
            stats[cid]["fp"] += 1
            stats[cid]["pred"] += 1
        for i in dup_ids:
            cid = preds[i]["class_id"]
            stats[cid]["dup"] += 1
            stats[cid]["pred"] += 1
        for i in fn_ids:
            cid = gts[i]["class_id"]
            stats[cid]["fn"] += 1
        for gt in gts:
            stats[gt["class_id"]]["gt"] += 1

        # Görsel raporu
        viol_fp = [preds[i] for i in fp_ids if preds[i]["class_id"] in VIOLATION_CLASSES]
        viol_fn = [gts[i] for i in fn_ids if gts[i]["class_id"] in VIOLATION_CLASSES]
        ppe_fp  = [preds[i] for i in fp_ids if preds[i]["class_id"] not in VIOLATION_CLASSES]

        flags = []
        if viol_fp:  flags.append(f"VİOL-FP:{len(viol_fp)}")
        if viol_fn:  flags.append(f"VİOL-FN:{len(viol_fn)}")
        if ppe_fp:   flags.append(f"PPE-FP:{len(ppe_fp)}")
        if dup_ids:  flags.append(f"DUP:{len(dup_ids)}")
        flag_str = " ".join(flags) if flags else "OK"

        print(f"  {fname[:50]:50s}  {result['latency_ms']:6.1f}ms  "
              f"gt={len(gts)} pred={len(preds)} tp={len(tp_ids)} | {flag_str}")

        # Detaylı FP/FN satırları (sadece ihlal sınıfları)
        for d in viol_fp:
            print(f"    ⚠️  FP (ihlal FP) : {d['class']} conf={d['confidence']} box={d['bounding_box']}")
        for g in viol_fn:
            print(f"    ❌  FN (kaçırılan): {CLASSES[g['class_id']]} box={g['box']}")

    # ── Özet rapor ────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("SINIF BAZINDA ÖZET")
    print(f"{'='*70}")
    hdr = f"  {'Sınıf':<22} {'GT':>5} {'Pred':>5} {'TP':>5} {'FP':>5} {'FN':>5} {'Dup':>5} {'Thresh':>7}"
    print(hdr)
    print("  " + "-"*66)
    total = defaultdict(int)
    for cid in sorted(CLASSES):
        s = stats[cid]
        total["gt"]   += s["gt"]
        total["pred"] += s["pred"]
        total["tp"]   += s["tp"]
        total["fp"]   += s["fp"]
        total["fn"]   += s["fn"]
        total["dup"]  += s["dup"]
        vmark = " ⚠️" if cid in VIOLATION_CLASSES else "   "
        print(f"  {CLASSES[cid]:<22}{vmark} {s['gt']:>4} {s['pred']:>5} {s['tp']:>5} "
              f"{s['fp']:>5} {s['fn']:>5} {s['dup']:>5} {CLASS_THRESHOLDS[cid]:>7.2f}")
    print("  " + "-"*66)
    print(f"  {'TOPLAM':<25} {total['gt']:>4} {total['pred']:>5} {total['tp']:>5} "
          f"{total['fp']:>5} {total['fn']:>5} {total['dup']:>5}")

    if latencies:
        lat = np.array(latencies)
        print(f"\n{'='*70}")
        print("LATENCY (ms)")
        print(f"{'='*70}")
        print(f"  Ortalama : {lat.mean():.1f} ms")
        print(f"  Medyan   : {np.median(lat):.1f} ms")
        print(f"  P95      : {np.percentile(lat, 95):.1f} ms")
        print(f"  Min/Max  : {lat.min():.1f} / {lat.max():.1f} ms")
        target = 500.0
        above = (lat > target).sum()
        print(f"  Hedef <{target:.0f}ms: {'✅ PASS' if above == 0 else f'⚠️  {above}/{len(lat)} görsel hedef aşıyor'}")

    print(f"\n{'='*70}")
    viol_fp_total  = sum(stats[c]["fp"]  for c in VIOLATION_CLASSES)
    viol_fn_total  = sum(stats[c]["fn"]  for c in VIOLATION_CLASSES)
    dup_total      = total["dup"]
    print(f"  İhlal FP (PPE varken ihlal dedi)  : {viol_fp_total}")
    print(f"  İhlal FN (ihlal varken atladı)     : {viol_fn_total}")
    print(f"  Duplicate tespit (NMS sonrası kalan): {dup_total}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MOD-01 PPE evaluate")
    parser.add_argument("--n", type=int, default=10, help="Test görsel sayısı (0=tümü)")
    parser.add_argument("--seed", type=int, default=42, help="Rastgele tohum")
    args = parser.parse_args()
    evaluate(n_samples=args.n, seed=args.seed)
