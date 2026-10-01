import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class names (shadcn convention). */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
