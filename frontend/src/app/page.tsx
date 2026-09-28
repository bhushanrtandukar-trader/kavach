"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useStatus } from "@/lib/hooks";

/** The root only decides where you belong. */
export default function Home() {
  const router = useRouter();
  const { data, isError } = useStatus();
  useEffect(() => {
    if (data) router.replace(data.initialized && data.me ? "/vaults" : "/login");
    else if (isError) router.replace("/login");
  }, [data, isError, router]);
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <div className="gradient-bg size-12 animate-pulse rounded-2xl" />
    </div>
  );
}
