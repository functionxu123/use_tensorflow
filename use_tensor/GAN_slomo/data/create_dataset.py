import cv2
import os
import os.path as op

#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
train_txt=r'./adobe240fps/train_list.txt'
test_txt=r'./adobe240fps/test_list.txt'
videodir=r'/media/sherl/本地磁盘/data_DL/Adobe240fps/original_high_fps_videos'
extratdir_train=r'/media/sherl/本地磁盘/data_DL/Adobe240fps/extracted_videos/train'
extratdir_test=r'/media/sherl/本地磁盘/data_DL/Adobe240fps/extracted_videos/test'
#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

def video2frame(videop, outpath):
    videoCapture=cv2.VideoCapture(videop)
    if not videoCapture.isOpened():
        print ('failed to open:',videop)
        return 0
    videorate = videoCapture.get(cv2.CAP_PROP_FPS)
    allcnt = videoCapture.get(cv2.CAP_PROP_FRAME_COUNT)  # 总帧数
    
    batcnt=0
    success, frame = videoCapture.read()  # 读取第一帧  
    print (frame.shape,'rate:',videorate,' framescnt:',allcnt)
    while success and batcnt <allcnt-1:  
        # frame = frame[0:1536,1200:1800]#截取画面  
        #videoCapture.set(cv2.CAP_PROP_POS_FRAMES, cnt)
                  
        
        tepd='%04d.jpg'%batcnt
        tepd=op.join(outpath, tepd)
        cv2.imwrite( tepd,frame)
        success, frame = videoCapture.read()  # 循环读取下一帧  
        batcnt+=1
        if not success: print ('read error:',batcnt,frame)
         
        
    videoCapture.release() 
    
    print ("done:",videop,':',str(batcnt))
    return batcnt
    

def txt2frames(txtpath, extratdir):
    cnt=0
    with open(txtpath,'r') as f:
        for i in f.readlines():
            tepi=i.strip()
            dirname=op.splitext(tepi)[0]
            movpath=op.join(videodir, tepi)
            outpath=op.join(extratdir, dirname)
            os.makedirs(outpath, exist_ok=True)
            resu=video2frame(movpath, outpath)
            cnt+=resu
        print (txtpath,'done:',cnt,' frames')
            
if __name__ == '__main__':
    txt2frames(train_txt ,extratdir_train)
    txt2frames(test_txt, extratdir_test)
            
            
            
            
            
            
            
            