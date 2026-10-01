import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";
import { facultyApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";

export const facultyKeys = {
  all: ["faculty"],
  dashboard: ["faculty", "dashboard"],
  profile: ["faculty", "profile"],
  classes: ["faculty", "classes"],
  classDetail: (id) => ["faculty", "class", String(id)],
  approvals: ["faculty", "approvals"],
  search: (q) => ["faculty", "student-search", q],
};

export const useFacultyDashboard = () => useQuery({ queryKey: facultyKeys.dashboard, queryFn: facultyApi.dashboard });
export const useFacultyProfile = () => useQuery({ queryKey: facultyKeys.profile, queryFn: facultyApi.profile });
export const useFacultyClasses = () => useQuery({ queryKey: facultyKeys.classes, queryFn: facultyApi.classes });
export const useClassDetail = (sectionId) =>
  useQuery({ queryKey: facultyKeys.classDetail(sectionId), queryFn: () => facultyApi.classDetail(sectionId) });
export const usePermissionRequests = () => useQuery({ queryKey: facultyKeys.approvals, queryFn: facultyApi.permissionRequests });

/** Drop every cached faculty view (dashboard counts, class lists, approvals) after something changed. */
export function useRefreshFaculty() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: facultyKeys.all });
    qc.invalidateQueries({ queryKey: queryKeys.session });
  };
}

/** Open (or create) the chat with a student, then go to the thread. */
export function useMessageStudent() {
  const navigate = useNavigate();
  return useMutation({
    mutationFn: (studentId) => facultyApi.openChat(studentId),
    onSuccess: (data) => navigate(`/faculty/chat/${data.chat_id}`),
    onError: (err) => toast.error(errorMessage(err)),
  });
}

/** Accept / reject a supporting-student request addressed to me. */
export function useRespondSupporting() {
  const refresh = useRefreshFaculty();
  return useMutation({
    mutationFn: ({ id, decision }) => facultyApi.respondSupporting(id, decision),
    onSuccess: (data) => {
      toast.success(data.message || "Done.");
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });
}
