"use client";

import { useEffect, type RefObject } from "react";
import hotkeys from "hotkeys-js";

export function useReviewHotkeys(host: RefObject<HTMLElement>, video: RefObject<HTMLVideoElement>,
  enabled: boolean, onMark: (key: "n" | "i" | "o") => void) {
  useEffect(() => {
    const element = host.current;
    if (!enabled || !element) return;
    const keys = "space,left,right,n,i,o";
    const handler = (event: KeyboardEvent, key: { key: string }) => {
      const target = event.target as HTMLElement;
      // Native inputs, buttons and video controls retain their keyboard behavior.
      if (event.repeat || target.closest("input,textarea,select,button,a,video,[contenteditable],[role='textbox']")) return;
      const player = video.current;
      if (!player || player.readyState < 1) return;
      event.preventDefault();
      if (key.key === "space") { if (player.paused) void player.play().catch(() => {}); else player.pause(); }
      else if (key.key === "left" || key.key === "right") player.currentTime = Math.max(0, Math.min(player.duration, player.currentTime + (key.key === "left" ? -5 : 5)));
      else onMark(key.key as "n" | "i" | "o");
    };
    hotkeys(keys, { element }, handler);
    return () => hotkeys.unbind(keys, handler);
  }, [host, video, enabled, onMark]);
}
