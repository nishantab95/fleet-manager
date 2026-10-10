import { redirect } from "next/navigation";

export default function OperationsRootPage() {
  redirect("/login?workspace=owner");
}
