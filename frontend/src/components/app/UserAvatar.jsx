import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { uploadUrl } from "@/lib/api";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

const SIZES = {
  xs: "size-7 text-[0.7rem]",
  sm: "size-9 text-[0.8125rem]",
  md: "size-11 text-[0.95rem]",
  lg: "size-14 text-lg",
  xl: "size-[104px] text-[2.1rem]",
};

/**
 * Profile picture, or initials on one of five palette colours (stable per name).
 * Decorative by default - the person's name is always shown next to it. Pass `alt` when it stands alone.
 *   <UserAvatar name={user.full_name} src={user.profile_picture_url} size="sm" />
 */
export function UserAvatar({ name, src, size = "md", alt = "", className }) {
  const palette = (name || "?").length % 5;
  return (
    <Avatar className={cn(SIZES[size] || SIZES.md, "border border-line", className)} aria-hidden={alt ? undefined : true}>
      {src ? <AvatarImage src={uploadUrl(src)} alt={alt} /> : null}
      <AvatarFallback className={cn("av-fill font-display font-bold", `av-${palette}`)}>{initials(name)}</AvatarFallback>
    </Avatar>
  );
}
