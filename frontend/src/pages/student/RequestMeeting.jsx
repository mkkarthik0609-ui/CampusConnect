import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/app/PageHeader";
import { FormField } from "@/components/app/FormField";
import { ListSkeleton } from "@/components/app/PageLoader";
import { Notice } from "@/components/app/Notice";
import { SubmitButton } from "@/components/app/SubmitButton";
import { UserAvatar } from "@/components/app/UserAvatar";
import { ApiError, errorMessage } from "@/lib/api";
import { meetingsApi, studentApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";

/** /student/meetings/request/:facultyId - ask a faculty member for time. They reply with a time in their own words. */
export default function RequestMeeting() {
  const { facultyId } = useParams();
  const id = Number.parseInt(facultyId, 10);
  const navigate = useNavigate();
  const qc = useQueryClient();

  // The dashboard already lists everyone this student can reach (class faculty + accepted supporting faculty).
  const dash = useQuery({ queryKey: queryKeys.studentDashboard, queryFn: studentApi.dashboard });
  const faculty = [...(dash.data?.assigned_faculty || []), ...(dash.data?.supporting_faculty || [])].find((f) => f.id === id);

  const [reason, setReason] = useState("");
  const [details, setDetails] = useState("");
  const [errors, setErrors] = useState({});

  const send = useMutation({
    mutationFn: (body) => meetingsApi.create(body),
    onSuccess: (res) => {
      toast.success(res.message || "Meeting request sent.");
      qc.invalidateQueries({ queryKey: queryKeys.meetings });
      qc.invalidateQueries({ queryKey: queryKeys.studentDashboard });
      navigate("/student/meetings?status=pending");
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields);
      else toast.error(errorMessage(err));
    },
  });

  function onSubmit(e) {
    e.preventDefault();
    const r = reason.trim();
    if (!r) return setErrors({ reason: "Say what you would like to discuss." });
    setErrors({});
    send.mutate({ faculty_id: id, reason: r, details: details.trim() || undefined });
  }

  const title = faculty ? `Request a meeting with ${faculty.full_name}` : "Request a meeting";

  return (
    <>
      <PageHeader title={title} back={{ to: "/student/dashboard", label: "Dashboard" }} />

      {dash.isPending ? (
        <ListSkeleton rows={2} />
      ) : dash.isError ? (
        <Notice tone="danger" title="Could not load this page">
          {dash.error.message}
          <Button variant="outline" size="sm" className="mt-2" onClick={() => dash.refetch()}>Try again</Button>
        </Notice>
      ) : !faculty ? (
        <Notice tone="warning" title="You cannot request a meeting with this faculty member yet">
          Meetings are open to the faculty assigned to your class and to faculty who accepted to support you.{" "}
          <Link to="/student/find-faculty" className="underline">Find faculty</Link> to send a supporting request.
        </Notice>
      ) : (
        <form onSubmit={onSubmit} noValidate className="grid max-w-2xl gap-5 rounded-lg border border-line bg-card p-[clamp(1rem,3vw,1.75rem)] shadow-sm">
          <div className="flex items-center gap-3">
            <UserAvatar name={faculty.full_name} src={faculty.profile_picture_url} size="md" />
            <p className="m-0 min-w-0">
              <span className="block font-[650]">{faculty.full_name}</span>
              <span className="block text-sm text-muted-foreground">
                <span className="font-mono">{faculty.faculty_code}</span>{faculty.department ? ` - ${faculty.department}` : ""}
              </span>
            </p>
          </div>
          <FormField label="Reason or topic" required error={errors.reason} hint={`${reason.trim().length}/200`}>
            <Input value={reason} maxLength={200} autoFocus placeholder="For example: Doubt in Assignment 3" onChange={(e) => { setReason(e.target.value); if (errors.reason) setErrors({}); }} />
          </FormField>
          <FormField label="Anything else they should know" error={errors.details} hint="Optional.">
            <Textarea rows={4} value={details} maxLength={2000} placeholder="Chapters, questions, how long you need" onChange={(e) => setDetails(e.target.value)} />
          </FormField>
          <p className="m-0 text-[0.9375rem] text-muted-foreground">
            There are no fixed slots. {faculty.full_name} will accept or decline and reply with a time in their own words.
          </p>
          <div className="flex flex-wrap gap-2">
            <SubmitButton loading={send.isPending}>Send request</SubmitButton>
            <Button asChild variant="outline"><Link to="/student/dashboard">Cancel</Link></Button>
          </div>
        </form>
      )}
    </>
  );
}
