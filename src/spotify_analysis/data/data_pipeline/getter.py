from abc import ABC, abstractmethod

class Getter[T](ABC):
    @abstractmethod
    def get_data(self) -> T:
        ...
        
class NullGetter(Getter[None]):
    def get_data(self) -> None:
        return None
    
class IdentityGetter[T](Getter[T]):
    def __init__(self, data: T):
        self.data = data
        
    def get_data(self) -> T:
        return self.data