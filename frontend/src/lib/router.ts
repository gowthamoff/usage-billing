// react-router helpers shared by the route pages.
import { useParams } from 'react-router-dom'

/**
 * Returns the named route param, throwing if it is absent.
 * Pages are only mounted under routes that define their params; a missing one is a routing bug, surfaced by the route errorElement.
 */
export function useRequiredParam(name: string): string {
  const params = useParams()
  const value = params[name]
  if (!value) throw new Error(`Missing route parameter "${name}"`)
  return value
}
