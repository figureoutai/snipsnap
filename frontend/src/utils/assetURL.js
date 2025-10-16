import { ASSET_BASE_URL } from "../constants/app.constants";

export function constructThumbnailURL(streamId, fileName = 'frame_000000000.jpg'){
    return `${ASSET_BASE_URL}${streamId}/images/frame/${fileName}`;
}

export function constructVideoURL(streamId, videoName) {
    return `${ASSET_BASE_URL}${streamId}/video/${videoName}`;
}