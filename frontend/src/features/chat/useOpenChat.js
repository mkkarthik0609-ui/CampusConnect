import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/auth/AuthProvider";
import { errorMessage } from "@/lib/api";
import { chatApi } from "@/lib/endpoints";

/**
 * Get-or-create the conversation with a person and go to it.
 *   const open = useOpenChat();
 *   <Button onClick={() => open.mutate(faculty.id)} disabled={open.isPending}>Message</Button>
 * Students pass a faculty id, faculty pass a student id. `open.variables` is the id being opened.
 */
export function useOpenChat() {
  const navigate = useNavigate();
  const { isStudent } = useAuth();
  return useMutation({
    mutationFn: (personId) => chatApi.open(isStudent ? { faculty_id: personId } : { student_id: personId }),
    onSuccess: (data) => navigate(`${isStudent ? "/student" : "/faculty"}/chat/${data.chat_id}`),
    onError: (err) => toast.error(errorMessage(err, "Could not open that conversation.")),
  });
}
