import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { Toaster as Sonner } from "sonner";
import { useTheme } from "@/lib/theme"

/**
 * Toasts (aria-live handled by sonner). Use `toast.success("Saved")`, `toast.error(errorMessage(err))`.
 * Themed to the ink & saffron tokens; follows the app theme.
 */
const Toaster = ({
  ...props
}) => {
  const { theme } = useTheme()

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      position="bottom-right"
      closeButton
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      toastOptions={{
        classNames: {
          toast: "!rounded-lg !border !font-sans !text-[0.9375rem] !font-medium !shadow-[var(--shadow-2)]",
          success: "!bg-ok !text-ok-ink !border-ok-line",
          error: "!bg-danger !text-danger-ink !border-danger-line",
          warning: "!bg-warn !text-warn-ink !border-warn-line",
          info: "!bg-info !text-info-ink !border-info-line",
        },
      }}
      style={
        {
          "--normal-bg": "var(--surface)",
          "--normal-text": "var(--ink)",
          "--normal-border": "var(--line)",
          "--border-radius": "12px"
        }
      }
      {...props}
    />
  );
}

export { Toaster }
