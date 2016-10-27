from operator import add
from threading import Thread,Lock
import Queue
import itertools
import barrier


"""
This module represents a cluster's computational node.

Computer Systems Architecture Course
Assignment 1 - Cluster Activity Simulation
March 2015
"""

class Node:
    """
    Class that represents a cluster node with computation and storage
    functionalities.
    """
    

    def __init__(self, node_id, data ):
        """
        Constructor.

        @type node_id: Integer
        @param node_id: the unique id of this node; between 0 and N-1

        @type data: List of Integer
        @param data: a list containing this node's data
        """
        self.node_id = node_id
        self.data = data
        self.nodes = None
        self.threads = []
        self.res=[]  # results -- rezultatele de la gather
        self.outs=[] # out slices
        self.queue = Queue.Queue() # coada pentru rezultatele de la task.run()
        self.barrier = None
        self.set_barrier_bool = 1 # folosit pentru partajarea barierei
        self.bestlock = Lock() # lock pt scrierea in node.data
        self.active_threads = [] # lista pt threadurile active
        

    def set_barrier(self,b):
        """
        setez barierele in nod
        @type b : ReusableBarrierSem()
        @param b: bariera partajata intre noduri

        """        
        self.barrier = b
        


    def gather(self,task,in_slices,out_slices):
        
        """ 
        intoarce pune in coada rezultatele taskului current
        @param task : taskul de rulat
        @param in_slices : in_slices (pasat de schedule_task)
        @param out_slices : out_slices            

        """
        
        result = []

        for lst in in_slices:
            
            (node,start,end) = lst
            result.append(self.nodes[node].get_data()[start:end]) # pun in result datele intre start-end de la nod
        
        
        result = list(itertools.chain.from_iterable(result)) # fac o lista -- flatten (lista de liste)        
        
        self.queue.put((task.run(result),out_slices))
        
 
    def __str__(self):
        """
        Pretty prints this node.

        @rtype: String
        @return: a string containing this node's id
        """
        return "Node %d" % self.node_id
    
    
    def set_cluster_info(self,  nodes):
        """
        Informs the current node about the supervisor and about the other
        nodes in the cluster.
        Guaranteed to be called before the first call to 'schedule_task'.

        @type nodes: List of Node
        @param nodes: a list containing all the nodes in the cluster
        """
        self.nodes = nodes
    
    
    def schedule_task(self, task, in_slices, out_slices):
        """
        Schedule task to execute on the node.
        
        @type task: Task
        @param task: the task object to execute

        @type in_slices: List of (Integer, Integer, Integer)
        @param in_slices: a list of the slices of data that need to be
            gathered for the task; each tuple specifies the id of a node
            together with the starting and ending indexes of the slice; the
            ending index is exclusive

        @type out_slices: List of (Integer, Integer, Integer)
        @param out_slices: a list of slices where the data produced by the
            task needs to be scattered; each tuple specifies the id of a node
            together with the starting and ending indexes of the slice; the
            ending index is exclusive
        """

 
   
        if(self.node_id==0 and self.set_barrier_bool==1):
            # partajeaza bariera - lucru de care se ocupa masterul (id==0)
            barr = barrier.ReusableBarrierSem(len(self.nodes))
            
            self.set_barrier_bool=0 # setez o singura data
            for n in self.nodes:
                n.set_barrier(barr)
                
        
        
        curr_thr = Thread(target = self.gather , args = (task,in_slices,out_slices)) # creare thread cu task
        
        
        
        if(len(self.active_threads) <= 16):
            # nu am inca 16 threaduri active, pot sa le pornesc
            self.active_threads.append(curr_thr)
            curr_thr.start()
        else:
            # am mai mult de 16 threaduri active, le pun pe "wait" pe restul
            self.threads.append(curr_thr)
    
    


    def sync_results(self):
        """
        Wait for scheduled tasks to finish and write results.
        """

        if(len(self.threads) > 0 ):
            done = 0 # nu mai am threaduri de rulat
        else:
            done = 1 # mai am threaduri "waiting"
        

        for t in self.active_threads:
            t.join()

        
        self.active_threads = []


        # cat timp mai sunt threaduri "waiting"
        while(done == 0):
           
            if(len(self.threads) >= 16):
                # mai dau start la 16 threaduri
                for i in range(16):
                    self.active_threads.append(self.threads.pop())
                    self.active_threads[i].start()

                for t in self.active_threads:
                    t.join()         

                self.active_threads = []       
                    
            else:
                # last threads waiting to run
                for t in self.threads:
                    t.start()
                done = 1
                
            
        for t in self.threads:
            t.join()
        #[______________________________________]
        
        


        # astept sa se termine toate gather-urile de la taskuri
        self.barrier.wait()
        
       

        # populare rezultate depuse in schedule_task      
        while(not self.queue.empty()):
            (item,out_sl) = self.queue.get()            
            self.res.append(item)
            self.outs.append(out_sl)
        #[______________________________________]            
        
        


        # scatter
        idx=0 # pentru parcurgerea res
        resst=0 # res start
        resend=0 # res end

        for ol in self.outs: # out slice list
            
            ctrl=0
            for o in ol:# 1 out_slice -- pt 1 task                    
                (node,start,end) = o
                ctrl += end-start
                
                resend = resst + (end-start) # pana unde
                
                # sectiune critica
                self.nodes[node].bestlock.acquire()
                self.nodes[node].data[start:end] = map(add,self.nodes[node].data[start:end] , self.res[idx][resst:resend] )
                self.nodes[node].bestlock.release()
                # ___

                resst = resend # de unde incep la iteratia urmatoare
               
            idx=idx+1 # urmatorul task din res
            resst = 0
           
        #[______________________________________] 


        
        # astept sa termine scatter
        self.barrier.wait()
        


        # s-a terminat runda ;; initializari pt runda urmatoare
        self.res=[]
        self.outs=[]
        self.queue = Queue.Queue()
        self.threads=[]
        #[______________________________________] 
        



    def get_data(self):
        """
        Return a copy of this node's data.
        """
        return self.data


    def shutdown(self):
        """
        Instructs the node to shutdown (terminate all threads). This method
        is invoked by the tester. This method must block until all the threads
        started by this node terminate.
        """
        pass
