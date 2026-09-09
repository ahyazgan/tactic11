"""Video takibi → TrackingFrame.

Katmanlar:
- calibration: görüntü pikseli ↔ saha metresi homografisi (saf numpy)
- teams: forma rengi kümeleme (saf numpy)
- frames: gözlemler → TrackingFrame (aynı şema; overlay değişmeden çalışır)
- detect / track / pipeline: RF-DETR + ByteTrack (torch gerektirir, tembel import;
  yalnız `venv-cv` işçisinde çalışır — ana uygulama import etmez)

Ağır bağımlılıklar bu paketin __init__'inde import EDİLMEZ.
"""
