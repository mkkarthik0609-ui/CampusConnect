import { useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Camera } from "lucide-react";
import { SubmitButton } from "@/components/app/SubmitButton";
import { UserAvatar } from "@/components/app/UserAvatar";
import { useAuth } from "@/auth/AuthProvider";
import { errorMessage } from "@/lib/api";
import { facultyApi } from "@/lib/endpoints";
import { useRefreshFaculty } from "@/features/faculty/hooks";

const MAX_BYTES = 3 * 1024 * 1024;
const TYPES = ["image/png", "image/jpeg"];

/** Avatar with a "Change photo" button. PNG / JPG up to 3 MB; the server re-checks the file content. */
export function PhotoUpload({ name, src }) {
  const input = useRef(null);
  const { patchUser } = useAuth();
  const refresh = useRefreshFaculty();

  const upload = useMutation({
    mutationFn: (file) => facultyApi.uploadPicture(file),
    onSuccess: (data) => {
      patchUser({ profile_picture_url: data.profile_picture_url });
      toast.success(data.message || "Profile picture updated.");
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  function onPick(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!TYPES.includes(file.type)) return toast.error("Choose a PNG or JPG image.");
    if (file.size > MAX_BYTES) return toast.error("That image is over 3 MB. Choose a smaller one.");
    upload.mutate(file);
  }

  return (
    <div className="flex items-center gap-4">
      <UserAvatar name={name} src={src} size="xl" alt={name ? `${name}, current profile photo` : "Profile photo"} />
      <div className="grid gap-1.5">
        <input ref={input} type="file" accept="image/png,image/jpeg" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={onPick} />
        <SubmitButton type="button" variant="outline" size="sm" loading={upload.isPending} loadingText="Uploading..." onClick={() => input.current?.click()}>
          <Camera aria-hidden="true" /> {src ? "Change photo" : "Add a photo"}
        </SubmitButton>
        <p className="m-0 text-[0.8125rem] text-muted-foreground">PNG or JPG, up to 3 MB.</p>
      </div>
    </div>
  );
}
