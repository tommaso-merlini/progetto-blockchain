import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const alertVariants = cva("rounded-md px-4 py-3 text-sm font-bold", {
  variants: {
    variant: {
      success: "bg-emerald-50 text-emerald-800",
      destructive: "bg-red-50 text-red-800",
    },
  },
  defaultVariants: {
    variant: "success",
  },
});

function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return <div className={cn(alertVariants({ variant }), className)} {...props} />;
}

export { Alert };
