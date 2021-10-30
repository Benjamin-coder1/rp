
import cv2, time, threading, multiprocessing                      
import numpy as np                       
import pyrealsense2 as rs                 # Intel RealSense cross-platform open-source API
import Parameters as p 
from Initialisation import * 


pool_obj = multiprocessing.Pool()


global verts
# Point cloud computation
def getPointCloud(depth_frame) : 
    global verts
    pc = rs.pointcloud()    
    points = pc.calculate(depth_frame)
    w = rs.video_frame(depth_frame).width
    h = rs.video_frame(depth_frame).height
    verts = np.asanyarray(points.get_vertices()).view(np.float32).reshape(h, w, 3)


def detect_obstacle() : 
    # This function is made to detect obstacle from the front camera, it is using
    # AI to detect obstacle from RGB camera then we use point cloud to localize obstacle
    # The camera used is a Realsense DepthCamera D435    

    ## Initialisation 
    Nbcsvt,Nbcsvt, frameNb = [0, 0, 0]

    # Starting camera
    pipe = rs.pipeline()
    align = rs.align(rs.stream.color)
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    cfg.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    pipe.start(cfg)
    Events.info("Camera connected and available ! ")
    cleanFrames()

    # Configure CNN
    net = cv2.dnn.readNetFromCaffe("./CaffeeModel/SSD_MobileNet.prototxt", "./CaffeeModel/SSD_MobileNet.caffemodel")
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
    inScaleFactor, meanVal , expected = [0.007843 , 127.53,  300]
    classNames = ("background", "aeroplane", "bicycle", "bird", "boat",
                "bottle", "bus", "car", "cat", "chair",
                "cow", "diningtable", "dog", "horse",
                "motorbike", "person", "pottedplant",
                "sheep", "sofa", "train", "tvmonitor")
    

    timel = []

    ## LOOP
    while not p.stop :

        t1 = time.time() 

        # Get data from camera 
        frameset = pipe.wait_for_frames()
        color_frame = frameset.get_color_frame()
        depth_frame = align.process(frameset).get_depth_frame()

        # Get img 
        color = np.asanyarray(color_frame.get_data()) 

        # Point cloud computation 
        GetPointCloud = threading.Thread(target=getPointCloud, args=(depth_frame,) )
        GetPointCloud.start()

        # Image processing computation 
        height, width = color.shape[:2]        
        aspect = width / height
        resized_image = cv2.resize(color, (round(expected * aspect), expected))
        crop_start = round(expected * (aspect - 1) / 2)
        crop_img = resized_image[0:expected, crop_start:crop_start+expected]
        blob = cv2.dnn.blobFromImage(crop_img, inScaleFactor, (expected, expected), meanVal, False)
        net.setInput(blob, "data")
        detections = net.forward("detection_out")
        
        # Join both 
        GetPointCloud.join()

        def po( i) : 
            # Get box bounding color 
            label = detections[0,0,i,1]
            xmin  = int(expected*detections[0,0,i,3])
            ymin  = int(expected*detections[0,0,i,4])
            xmax  = int(expected*detections[0,0,i,5])
            ymax  = int(expected*detections[0,0,i,6])
            xmil = int( (xmax - xmin)/2 + xmin)
            ymil = int( (ymax - ymin)/2 + ymin)
           
            # Get box bounding depth 
            scale = height / expected
            xminD = int((expected*detections[0,0,i,3] + crop_start)*scale )
            xmaxD = int((expected*detections[0,0,i,5] + crop_start)*scale )
            yminD = int((expected*detections[0,0,i,4])*scale )
            ymaxD = int((expected*detections[0,0,i,6])*scale ) 
            xmilD = int((xmil + crop_start)*scale )
            ymilD = int((ymil)*scale )    

            # Next device
            i += 1
          
            # Work only for bottles
            if classNames[int(label)] != "bottle" : 
                return

            try : 
                # Look for min 
                Tab = verts[yminD:ymaxD, xminD:xmaxD,:]
                Tab = np.reshape( Tab , (np.prod( np.shape(Tab)[0:2] ) , 3) )[:,2]
                minDepth = min( Tab[Tab > 0])

                # Look for center 
                ks = 4
                for yD in range(ymilD - ks, ymilD + ks ) : 
                    for xD in range(xmilD - ks, xmilD + ks ) :            
                        if verts[yD, xD, 2] != 0 :
                            milyDi, milxDi = [yD, xD]               

                milyD, milxD, _ = verts[ milyDi, milxDi , : ]
                milxD, zD = -milxD, minDepth
                milxi = int((milxDi/scale - crop_start) )
                milyi = int(milyDi/scale )
                
                pos = str(round(milxD,2))+ ' ' + str(round(milyD,2)) + ' ' + str(round(zD,2))
                cv2.circle(crop_img, ( milxi , milyi ), 3, (255,0,0), -1)
                cv2.rectangle(crop_img, (xmin, ymin), (xmax, ymax), (0, 0, 0), 2)
                cv2.putText(crop_img, pos, (xmin - 30, ymin - 10), cv2.FONT_HERSHEY_COMPLEX, 0.4, (0, 0, 0) )
                Nbcsvt = 0
                if zD < p.distMin : 
                    if Nbcsvt < 5 :     Nbcsvt += 1
                    else :  p.stop = True
            except : 
                pass


        pool_obj.map(po,range(3))
        timel.append( time.time() - t1)
        print( time.time() - t1)
        
            
        
        

        # diplay image 
        frameNb += 1
        cv2.imwrite('frames/frame_' + str(frameNb) + '.png', crop_img)
        cv2.imshow('image', crop_img)
        cv2.waitKey(1)

    print("\033[93m" + "--***--  OBSTACLE DETECTED / STOP  --***-" + "\033[0m")
    print(np.mean(timel))


detect_obstacle()

