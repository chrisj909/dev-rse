type LeafletModule = typeof import('leaflet');

type LeafletImportModule = LeafletModule & {
  default?: LeafletModule;
};

type GlobalWithLeaflet = typeof globalThis & {
  L?: LeafletModule | undefined;
};

let leafletRuntimePromise: Promise<LeafletModule> | null = null;

export async function loadLeafletRuntime(): Promise<LeafletModule> {
  if (!leafletRuntimePromise) {
    leafletRuntimePromise = (async () => {
      const leafletImport = await import('leaflet') as LeafletImportModule;
      const leaflet = 'default' in leafletImport && leafletImport.default
        ? leafletImport.default
        : leafletImport;
      const globalWithLeaflet = globalThis as GlobalWithLeaflet;

      globalWithLeaflet.L = leaflet;
      await import('leaflet.markercluster');

      return globalWithLeaflet.L ?? leaflet;
    })().catch((error) => {
      leafletRuntimePromise = null;
      throw error;
    });
  }

  return leafletRuntimePromise;
}

export function resetLeafletRuntimeForTest(): void {
  leafletRuntimePromise = null;
  Reflect.deleteProperty(globalThis as Record<string, unknown>, 'L');
}