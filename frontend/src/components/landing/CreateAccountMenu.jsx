import { Link } from "react-router-dom";
import { ChevronDown, GraduationCap, Presentation } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

/**
 * "Create account" menu: students and faculty register differently, so the choice is explicit.
 * `plain` renders a bare text button (for the footer link column) instead of a Button.
 */
export function CreateAccountMenu({ variant = "default", size = "default", className, align = "end", side = "bottom", plain = false }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {plain ? (
          <button type="button" className={className}>Create account</button>
        ) : (
          <Button variant={variant} size={size} className={className}>
            Create account <ChevronDown aria-hidden="true" />
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} side={side} className="min-w-60">
        <DropdownMenuItem asChild>
          <Link to="/signup/student" className="no-underline"><GraduationCap aria-hidden="true" /> I'm a student</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/signup/faculty" className="no-underline"><Presentation aria-hidden="true" /> I'm faculty</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
