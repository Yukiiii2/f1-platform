import { accountState } from "../_lib/auth-api";
import { AccountControls } from "./account-controls";
export async function AccountNavigation() {
  return <AccountControls {...await accountState()} />;
}
