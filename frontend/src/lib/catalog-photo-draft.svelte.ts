import { api, updateCatalogPhotoFraming, uploadCatalogPhoto } from './api';
import type { PhotoFraming } from './types';

type ItemWithPhoto = { photo_path: string | null; photo_framing: PhotoFraming | null };

export class CatalogPhotoDraft {
  file = $state<File | null>(null);
  framing = $state<PhotoFraming | null>(null);
  removeOnSave = $state(false);
  private baseline = $state('null');

  private get framingChanged() {
    return JSON.stringify(this.framing) !== this.baseline;
  }

  get dirty() {
    return this.file !== null || this.removeOnSave || this.framingChanged;
  }

  reset(item: ItemWithPhoto) {
    this.file = null;
    this.framing = item.photo_framing;
    this.baseline = JSON.stringify(item.photo_framing);
    this.removeOnSave = false;
  }

  async save<T extends ItemWithPhoto>(path: string, item: T): Promise<T> {
    if (this.file) return uploadCatalogPhoto<T>(path, this.file, this.framing);
    if (this.removeOnSave && item.photo_path) return api<T>(path, { method: 'DELETE' });
    if (this.framingChanged) {
      return updateCatalogPhotoFraming<T>(path, this.framing);
    }
    return item;
  }
}
