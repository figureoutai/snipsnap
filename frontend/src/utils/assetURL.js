import { ASSET_BASE_URL } from "../constants/app.constants";

export function constructThumbnailURL(streamId, fileName = 'frame_000000000.jpg'){
    return `${ASSET_BASE_URL}${streamId}/images/frame/${fileName}`;
}

export function constructVideoURL(streamId, videoName) {

    let fileName;
    const lastDotIndex = videoName.lastIndexOf('.');
    if(lastDotIndex === -1){
        fileName = videoName;
    }else{
        fileName = videoName.substring(0, lastDotIndex);
    }

    return `${ASSET_BASE_URL}${streamId}/video/${fileName}.m3u8`;
}