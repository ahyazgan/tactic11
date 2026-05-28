/**
 * className merge — clsx + tailwind-merge.
 * package.json'da `clsx` ve `tailwind-merge` zaten var.
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
