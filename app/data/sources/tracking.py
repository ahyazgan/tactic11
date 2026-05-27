"""Tracking veri kaynağı sözleşmesi — [BOŞ İSKELET, Faz 6'da doldurulacak].

Kulüp tracking sağlayıcısının (örn. SecondSpectrum, Hawk-Eye, kulübün kendi
sistemi) adapter'ları bu sınıftan türer. Sözleşme `data/sources/base.py`'deki
`DataSource`'tan KASIRTLI olarak ayrıdır — tracking verisinin akış şekli
(zaman serisi, yüksek frekans) league/team/match adapter'ından temelden farklı.

Şimdilik sadece imzalar; mantık yok. Faz 6'da bir somut adapter
(`SecondSpectrumAdapter` vb.) bu interface'i doldurur.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.domain import TrackingFrame


class TrackingDataSource(ABC):
    """Bir tracking sağlayıcısını temsil eden adapter sözleşmesi."""

    name: str  # ör: "second_spectrum", "hawkeye", "club_internal"

    @abstractmethod
    def get_match_frames(
        self,
        match_external_id: int,
        *,
        period: int | None = None,
    ) -> Iterable[TrackingFrame]:
        """Bir maçın tracking frame'lerini döner.

        Iterable döndürme tercihi: tipik maç ~135k frame; tek listede tutmak
        yerine streaming/batch işleme. Adapter generator ya da chunked liste
        verebilir; ingest tarafında loop ile tüketilir.
        """
