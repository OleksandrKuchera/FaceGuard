export interface DemoCamera {
  id: number;
  name: string;
  location: string;
}

const STORAGE_KEY = 'fg_demo_cameras';

export function loadDemoCameras(): DemoCamera[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as DemoCamera[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveDemoCameras(cameras: DemoCamera[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cameras));
}

export function getDemoCameraById(id: number): DemoCamera | null {
  return loadDemoCameras().find(camera => camera.id === id) ?? null;
}
